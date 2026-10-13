"""Executed only by Blender's embedded Python; requires a reviewed GLB.

Contract: imported GLB has UV-mapped mesh surfaces named
ALF_DECAL_left_chest, ALF_DECAL_back, etc., at the correct garment positions.
Approval/geometry preparation must be done by a clothing 3D artist.
"""
import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector


def stage(name):
    print('ALF_STAGE:'+name, flush=True)


def material_color(c):
    c=c.lstrip('#')
    if len(c)!=6:raise ValueError('Invalid garment color')
    channels=[int(c[i:i+2],16)/255 for i in (0,2,4)]
    def gamma(v): return v/12.92 if v<.04045 else ((v+.055)/1.055)**2.4
    return tuple(gamma(v) for v in channels)+(1,)


def camera_target_and_extent(objects):
    points=[obj.matrix_world @ Vector(corner) for obj in objects if obj.type=='MESH' for corner in obj.bound_box]
    if not points:raise RuntimeError('Approved GLB contains no mesh')
    x=[v.x for v in points]; y=[v.y for v in points];z=[v.z for v in points]
    center=Vector(((min(x)+max(x))/2,(min(y)+max(y))/2,(min(z)+max(z))/2))
    extent=max(max(x)-min(x),max(y)-min(y),max(z)-min(z),.5)
    return center,extent


def aim_camera(camera,focus,position):
    camera.location=position
    direction=focus-position
    camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()


def main(cfg):
    scene=bpy.context.scene
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    stage('PREPARING_GARMENT')
    bpy.ops.import_scene.gltf(filepath=cfg['glb_path'])
    imported=[o for o in scene.objects if o.type=='MESH']
    if not imported:raise RuntimeError('No garment geometry in approved asset')
    approved_surfaces={o.name[len('ALF_DECAL_'):]:o for o in imported if o.name.startswith('ALF_DECAL_')}
    # All selected logo patches must already exist as physically positioned UV mesh decals.
    requested={x['name'] for x in cfg['placements']}
    if requested.difference(approved_surfaces):
        raise RuntimeError('Model lacks required UV decal surfaces: '+','.join(sorted(requested.difference(approved_surfaces))))
    # Hide unselected decals; prevent leftover placeholder patches in final output.
    for name,mesh in approved_surfaces.items():
        mesh.hide_render=(name not in requested)
        mesh.hide_set(name not in requested)
    stage('APPLYING_BRANDING')
    image=bpy.data.images.load(cfg['logo_path'],check_existing=False)
    method=cfg['branding_method']
    for setting in cfg['placements']:
        obj=approved_surfaces[setting['name']]
        # Artist-authored decal object origin must be at the branding zone center.
        # 0.14 = approved authoring reference scale, enforced by the manifest.
        obj.scale = tuple(axis * (float(setting['scale']) / 0.14) for axis in obj.scale)
        if not obj.data.uv_layers:raise RuntimeError('Missing UV on ALF_DECAL_'+setting['name'])
        mat=bpy.data.materials.new('ALF_'+method+'_'+setting['name']);mat.use_nodes=True
        nodes=mat.node_tree.nodes;nodes.clear(); links=mat.node_tree.links
        out=nodes.new('ShaderNodeOutputMaterial')
        shader=nodes.new('ShaderNodeBsdfPrincipled')
        tex=nodes.new('ShaderNodeTexImage');tex.image=image;tex.interpolation='Linear'
        links.new(tex.outputs['Color'],shader.inputs['Base Color']);links.new(tex.outputs['Alpha'],shader.inputs['Alpha'])
        shader.inputs['Roughness'].default_value=0.70 if method=='embroidery' else 0.38 if method=='dtf' else 0.64
        # Professional garment decals are UV mapped. Thread-like bump is a visually
        # plausible shader ONLY, not embroidery digitization / manufacturing proof.
        if method=='embroidery':
            coord=nodes.new('ShaderNodeTexCoord')
            wave=nodes.new('ShaderNodeTexWave');wave.wave_type='BANDS';wave.bands_direction='DIAGONAL'
            wave.inputs['Scale'].default_value=230.0
            bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22
            bump.inputs['Distance'].default_value=.003
            links.new(coord.outputs['UV'],wave.inputs['Vector'])
            links.new(wave.outputs['Color'],bump.inputs['Height'])
            links.new(bump.outputs['Normal'],shader.inputs['Normal'])
        links.new(shader.outputs['BSDF'],out.inputs['Surface'])
        obj.data.materials.clear();obj.data.materials.append(mat)
    # Only materials explicitly marked ALF_COLOR_FABRIC get recolored.
    color=material_color(cfg['garment_hex'])
    for material in bpy.data.materials:
        if material.name.startswith('ALF_COLOR_FABRIC'):
            material.diffuse_color=color
            if material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type=='BSDF_PRINCIPLED':node.inputs['Base Color'].default_value=color
    # Configure Cycles and the neutral studio: stable repeatable white balance.
    scene.render.engine='CYCLES';scene.cycles.samples=int(cfg['samples'])
    scene.render.resolution_x=int(cfg['resolution']);scene.render.resolution_y=int(cfg['resolution'])
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.render.film_transparent=False
    scene.world.color=(.27,.27,.27)
    scene.view_settings.view_transform='AgX'
    focus,span=camera_target_and_extent(imported)
    for name,pos,size,power in [('key',(3,-4,6),4,450),('fill',(-3,-2,4),4,320),('rim',(0,3,5),3,480)]:
        light=bpy.data.lights.new(name,type='AREA');light.energy=power*(span**2);light.shape='DISK';light.size=size*span
        ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob)
        ob.location=focus+Vector(pos)*span*.6
        ob.rotation_euler=(focus-ob.location).to_track_quat('-Z','Y').to_euler()
    # Asset contract: front of approved GLB points -Y; +Y is back.
    camera_data=bpy.data.cameras.new('ALF Studio Camera')
    camera=bpy.data.objects.new('ALF Studio Camera',camera_data);scene.collection.objects.link(camera)
    camera_data.type='ORTHO';camera_data.ortho_scale=span*1.55;scene.camera=camera
    dist=span*2.7
    output=Path(cfg['output_dir'])
    for name,direction in [('front',(0,-1,.22)),('back',(0,1,.22)),('angle',(0.65,-1,.23))]:
        stage('RENDERING_'+name.upper())
        aim_camera(camera,focus,focus+Vector(direction).normalized()*dist)
        scene.render.filepath=str(output/(name+'.png'))
        bpy.ops.render.render(write_still=True)
    stage('OPTIMIZING_MODEL')
    # Hide stage props in GLB and export garment geometry with decorated UV decals.
    for o in scene.objects:
        o.select_set(False)
    for o in imported:o.hide_set(False);o.select_set(not o.hide_render)
    bpy.context.view_layer.objects.active=next((o for o in imported if not o.hide_render),None)
    bpy.ops.export_scene.gltf(filepath=str(output/'model.glb'),export_format='GLB',use_selection=True,
                              export_yup=True)
    stage('FINALIZING')

if __name__=='__main__':
    if '--' not in sys.argv:raise ValueError('Expected render configuration filename')
    data=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text())
    main(data)
