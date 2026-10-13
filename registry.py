"""Constrained garment model registry. Assets tagged provisional are NOT customer-grade."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Garment:
    category: str
    label: str
    model: str
    name: str
    placements: tuple
    methods: tuple = ('embroidery', 'dtf', 'screen_print')
    approved: bool = False

GARMENTS = [
    Garment('ALF-01','Polo Shirts & T-Shirts','polo','Polo / T-Shirt',('left_chest','right_chest','center_chest','back','sleeve')),
    Garment('ALF-02','Chef Uniforms & Aprons','chef_jacket','Chef Jacket',('left_chest','right_chest','back','sleeve','apron_center')),
    Garment('ALF-03','Chef Caps & Accessories','chef_cap','Chef Cap',('cap_front','cap_side')),
    Garment('ALF-04','Cargo Pants & Workwear','workwear','Cargo Workwear Jacket',('left_chest','right_chest','back','sleeve','workwear_pocket')),
    Garment('ALF-05','Security Uniforms','security','Security Shirt',('left_chest','right_chest','back','sleeve')),
    Garment('ALF-06','Corporate Shirts','corporate','Corporate Shirt',('left_chest','right_chest','back','sleeve')),
    Garment('ALF-07','Event & Promo Team Apparel','event','Event / Promotional Tee',('left_chest','right_chest','center_chest','back','sleeve')),
]
BY_CATEGORY={g.category:g for g in GARMENTS}
BY_MODEL={g.model:g for g in GARMENTS}
LABEL_TO_ID={g.label:g.category for g in GARMENTS}
ALLOWED_COLORS = {'navy':'#152a4b','black':'#20242c','white':'#e6ecf0','royal blue':'#2455a8','red':'#9e2d3f','grey':'#636c76','charcoal':'#363d48','beige':'#c2b297','green':'#385a45'}

def public_registry(prototypes=False):
    return {'categories':[{'id':g.category,'label':g.label,'model_id':g.model,'subtype':g.name,'placements':g.placements,'methods':g.methods,'approved':g.approved,'available_for_generation':g.approved or prototypes} for g in GARMENTS], 'provisional_mode':prototypes}
