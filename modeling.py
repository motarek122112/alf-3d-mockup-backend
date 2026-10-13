"""Deterministic 3D **PROVISIONAL** garment geometry for integration tests.

These meshes are distinguishable by category but not physically approved/photoreal.
Replace in production with manufacturer-specific garments and garment-specific UVs.
"""
import math
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import trimesh
from shapely.geometry import Polygon
from shapely.ops import triangulate

# silhouette profiles in x,z; front faces point forward toward -Y
TORSO=[(-.40,0),(.40,0),(.43,.85),(.57,.82),(.89,.58),(1.07,.88),(.71,1.26),(.36,1.29),(.20,1.20),(0,1.12),(-.20,1.20),(-.36,1.29),(-.71,1.26),(-1.07,.88),(-.89,.58),(-.57,.82),(-.43,.85)]
CHEF=[(-.48,0),(.48,0),(.49,.82),(.66,.79),(.93,.51),(1.13,.99),(.76,1.37),(.37,1.41),(.20,1.32),(0,1.23),(-.20,1.32),(-.37,1.41),(-.76,1.37),(-1.13,.99),(-.93,.51),(-.66,.79),(-.49,.82)]
CAP=[(-.56,.52),(.56,.52),(.56,.82),(.40,1.13),(-.40,1.13),(-.56,.82)]
WORK=[(-.52,0),(.52,0),(.50,.94),(.68,.91),(.98,.55),(1.20,.96),(.78,1.42),(.36,1.44),(.18,1.34),(0,1.23),(-.18,1.34),(-.36,1.44),(-.78,1.42),(-1.20,.96),(-.98,.55),(-.68,.91),(-.50,.94)]
SECURITY=[(-.47,0),(.47,0),(.45,.94),(.66,.90),(.97,.58),(1.14,.93),(.72,1.35),(.36,1.40),(.18,1.3),(0,1.22),(-.18,1.3),(-.36,1.40),(-.72,1.35),(-1.14,.93),(-.97,.58),(-.66,.90),(-.45,.94)]
CORPORATE=[(-.38,0),(.38,0),(.44,.92),(.62,.90),(.93,.55),(1.10,.90),(.69,1.32),(.31,1.34),(.15,1.23),(0,1.1),(-.15,1.23),(-.31,1.34),(-.69,1.32),(-1.10,.90),(-.93,.55),(-.62,.90),(-.44,.92)]
EVENT=[(-.41,0),(.41,0),(.45,.82),(.61,.78),(.91,.52),(1.05,.79),(.72,1.2),(.30,1.22),(.18,1.13),(0,1.06),(-.18,1.13),(-.30,1.22),(-.72,1.20),(-1.05,.79),(-.91,.52),(-.61,.78),(-.45,.82)]
PROFILES={'polo':TORSO,'chef_jacket':CHEF,'chef_cap':CAP,'workwear':WORK,'security':SECURITY,'corporate':CORPORATE,'event':EVENT}
ZONES={'left_chest':(-.23,.93),'right_chest':(.23,.93),'center_chest':(0,.79),'back':(0,.73),'sleeve':(.78,.97),'apron_center':(0,.42),'cap_front':(0,.77),'cap_side':(.3,.77),'workwear_pocket':(-.27,.65)}

def extrude_profile(profile,depth=.13):
    poly=Polygon(profile);coords=list(poly.exterior.coords)[:-1]
    # use Shapely constrained triangle test to handle concave collar geometry
    triangles=[tri for tri in triangulate(poly) if poly.covers(tri.representative_point())]
    vertices=[];faces=[];lookup={}
    def vid(x,y,z):
        key=(round(x,7),round(y,7),round(z,7))
        if key not in lookup: lookup[key]=len(vertices);vertices.append(key)
        return lookup[key]
    for tri in triangles:
        pt=list(tri.exterior.coords)[:3]
        faces.append([vid(x,-depth/2,z) for x,z in pt][::-1])
        faces.append([vid(x, depth/2,z) for x,z in pt])
    for (a,b) in zip(coords, coords[1:]+coords[:1]):
        x,z=a; x2,z2=b
        f1=vid(x,-depth/2,z);f2=vid(x2,-depth/2,z2);b1=vid(x,depth/2,z);b2=vid(x2,depth/2,z2)
        faces.extend([[f1,f2,b2],[f1,b2,b1]])
    m=trimesh.Trimesh(vertices=np.asarray(vertices,dtype=float),faces=np.asarray(faces,dtype=int),process=False)
    return m

def material_color(hex_color):
    h=hex_color.lstrip('#')
    return tuple(int(h[k:k+2],16) for k in (0,2,4))

def create_scene(model,color,logo,method='embroidery',placements=('left_chest',),logo_scale=.14):
    if model not in PROFILES:raise ValueError('Unrecognized garment model')
    rgb=material_color(color);scene=trimesh.Scene()
    garment=extrude_profile(PROFILES[model]);garment.visual.face_colors=[*rgb,255]
    scene.add_geometry(garment,node_name='garment',geom_name='garment')
    # category-specific panels and seams (provisional, no manufacturer-specific accuracy)
    if model in ('chef_jacket','corporate','security','workwear'):
        for sign in (-1,1):
            pocket=trimesh.creation.box(extents=(.24,.012,.19));pocket.apply_translation((sign*.26,-.08,.68))
            pocket.visual.face_colors=[max(0,x-15) for x in rgb]+[255]
            scene.add_geometry(pocket,geom_name=f'pocket_{sign}')
    if model=='chef_jacket':
        for i in range(4):
            for x in (-.12,.12):
                b=trimesh.creation.icosphere(subdivisions=1,radius=.015);b.apply_translation((x,-.09,.45+i*.15));b.visual.vertex_colors=[232,238,239,255];scene.add_geometry(b)
    if model=='security':
        for x in (-.27,.27):
            patch=trimesh.creation.box(extents=(.18,.014,.04));patch.apply_translation((x,-.084,1.07));patch.visual.face_colors=[183,191,201,255];scene.add_geometry(patch)
    if model=='chef_cap':
        band=trimesh.creation.box(extents=(1.12,.15,.12));band.apply_translation((0,-.02,.62));band.visual.face_colors=[max(0,k-12) for k in rgb]+[255];scene.add_geometry(band)
    if model=='polo':
        # short collar slabs
        for sign in (-1,1):
            cc=trimesh.creation.box(extents=(.23,.03,.075));cc.apply_translation((sign*.135,-.08,1.19));cc.visual.face_colors=[max(0,k-17) for k in rgb]+[255];scene.add_geometry(cc)
    texture=logo.convert('RGBA')
    if method=='embroidery':
        # preview textured with stitch-like diagonal grain, not actual embroidery digitization
        from PIL import ImageDraw
        tint=Image.new('RGBA',texture.size,(0,0,0,0)); d=ImageDraw.Draw(tint)
        for q in range(-texture.height,texture.width+texture.height,8):d.line((q,0,q+texture.height,texture.height),fill=(245,245,245,32),width=2)
        texture=Image.alpha_composite(texture,tint)
    elif method=='screen_print': texture=ImageEnhance.Contrast(texture).enhance(1.12)
    for index,placement in enumerate(placements):
        if placement not in ZONES:continue
        x,z=ZONES[placement];is_back=(placement=='back')
        ypos=.087 if is_back else -.087
        h=max(.055,min(.35,logo_scale))
        if model=='chef_cap':h=min(h,.16)
        width=h*min(texture.width/texture.height,3)
        corners=np.array([[x-width/2,ypos,z+h/2],[x+width/2,ypos,z+h/2],[x+width/2,ypos,z-h/2],[x-width/2,ypos,z-h/2]])
        decal=trimesh.Trimesh(vertices=corners,faces=[[0,1,2],[0,2,3]],process=False)
        decal.visual=trimesh.visual.TextureVisuals(uv=[[0,0],[1,0],[1,1],[0,1]],image=texture)
        scene.add_geometry(decal,node_name=f'logo_{index}',geom_name=f'logo_{placement}_{index}')
    return scene
