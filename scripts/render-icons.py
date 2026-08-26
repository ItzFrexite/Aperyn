#!/usr/bin/env python3
"""Render deterministic PWA tiles for Nym, Aperyn's signal-moth mascot."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'chat/static/icons'
OUT.mkdir(parents=True,exist_ok=True)

def render(size):
    scale=size/64
    image=Image.new('RGBA',(size,size),(9,13,20,255))
    draw=ImageDraw.Draw(image)
    # Quiet accent refraction behind a strictly white foreground mark.
    for radius,alpha in ((27,18),(22,22)):
        layer=Image.new('RGBA',(size,size),(0,0,0,0)); ld=ImageDraw.Draw(layer)
        r=radius*scale; ld.ellipse((size/2-r,size/2-r,size/2+r,size/2+r),fill=(120,169,255,alpha))
        image=Image.alpha_composite(image,layer)
    draw=ImageDraw.Draw(image)
    # Nym's wings form a compact A-like silhouette; the antennae carry the signal motif.
    wing=[(28,23),(23,18),(16,17),(11,22),(8,31),(9,39),(16,45),(23,45),(28,41),(32,36),
          (36,41),(41,45),(48,45),(55,39),(56,31),(53,22),(48,17),(41,18),(36,23),(32,21)]
    draw.polygon([(x*scale,y*scale) for x,y in wing],fill='white')
    draw.ellipse((22*scale,17*scale,42*scale,38*scale),fill='white')
    draw.polygon([(27*scale,34*scale),(29*scale,51*scale),(32*scale,57*scale),(35*scale,51*scale),(37*scale,34*scale)],fill='white')
    ant_width=max(1,round(4*scale))
    draw.line([(27*scale,19*scale),(23*scale,12*scale),(18*scale,12*scale),(15*scale,7*scale)],fill='white',width=ant_width,joint='curve')
    draw.line([(37*scale,19*scale),(41*scale,12*scale),(46*scale,12*scale),(49*scale,7*scale)],fill='white',width=ant_width,joint='curve')
    eye=max(1,round(2.4*scale))
    draw.line([(27*scale,27.5*scale),(29*scale,27.5*scale)],fill=(9,13,20,255),width=eye)
    draw.line([(35*scale,27.5*scale),(37*scale,27.5*scale)],fill=(9,13,20,255),width=eye)
    draw.line([(29*scale,33*scale),(31*scale,35*scale),(33*scale,35*scale),(35*scale,33*scale)],fill=(9,13,20,255),width=eye,joint='curve')
    image.save(OUT/f'icon-{size}.png',optimize=True)

for value in (192,512): render(value)
