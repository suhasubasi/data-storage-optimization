"""Presentation-region detection, independent of file/slide deduplication.

Only a large light rectangular panel with clean edges is automatically cropped.
Dark/ambiguous layouts retain the full image; explicit normalized coordinates
are available for those layouts. No global similarity threshold is relaxed.
"""
from __future__ import annotations

import numpy as np
from PIL import Image,ImageDraw


def _runs(mask):
    result,start=[],None
    for i,value in enumerate([*mask,False]):
        if value and start is None:
            start=i
        elif not value and start is not None:
            result.append((start,i))
            start=None
    return result


def _closed(mask,gap):
    mask=list(mask)
    for start,end in _runs([not value for value in mask]):
        if start and end<len(mask) and end-start<=gap:
            mask[start:end]=[True]*(end-start)
    return mask


def presentation_box(image: Image.Image, configured=None):
    w,h=image.size
    if configured is not None:
        if len(configured)!=4 or not (0<=configured[0]<configured[2]<=1 and 0<=configured[1]<configured[3]<=1):
            raise ValueError("presentation_region must be normalized [left, top, right, bottom]")
        box=tuple(round(value*size) for value,size in zip(configured,(w,h,w,h)))
        if box[2]<=box[0] or box[3]<=box[1]:
            raise ValueError("presentation_region is empty")
        return box
    if min(w,h)<100:
        return None
    pixels=np.asarray(image.convert("RGB"))
    light=pixels.min(axis=2)>=160
    candidates=[]
    for top,bottom in _runs(_closed(light.mean(axis=1)>=.4,max(2,round(h*.015)))):
        if bottom-top<h*.4:
            continue
        columns=_closed(light[top:bottom].mean(axis=0)>=.65,max(2,round(w*.01)))
        for left,right in _runs(columns):
            area=(right-left)*(bottom-top)
            if not (.4*w*h<=area<.98*w*h and 1.2<=(right-left)/(bottom-top)<=2.1):
                continue
            # A white chart inside a dark slide is not a presentation panel.
            # Prefer the large edge-aligned screen-share layout; otherwise keep
            # the entire frame instead of guessing away titles or annotations.
            if not ((left<=w*.02 or right>=w*.98) and bottom-top>=h*.75):
                continue
            edges=[light[top,left:right].mean(),light[bottom-1,left:right].mean(),
                   light[top:bottom,left].mean(),light[top:bottom,right-1].mean()]
            if min(edges)<.95:
                continue
            outside=[]
            if top: outside.append(pixels[max(0,top-2):top,left:right])
            if bottom<h: outside.append(pixels[bottom:min(h,bottom+2),left:right])
            if left: outside.append(pixels[top:bottom,max(0,left-2):left])
            if right<w: outside.append(pixels[top:bottom,right:min(w,right+2)])
            if outside and min((band.min(axis=2)<120).mean() for band in outside)>=.85:
                candidates.append((area,(left,top,right,bottom)))
    if len(candidates)==1:
        return candidates[0][1]
    return None


def presentation_image(image: Image.Image, configured=None):
    box=presentation_box(image,configured)
    return image.crop(box) if box is not None else image


def cursor_mask(image: Image.Image):
    """Recognize a black-outline/white-fill mouse arrow, not arbitrary small changes.

    This is only used for pairs where one recognized pointer is present in BOTH
    images at different positions. Unknown shapes and appearing arrows stay visible.
    """
    from scipy.signal import fftconvolve
    pixels=np.asarray(image.convert("RGB"))
    dark=(pixels.max(axis=2)<70).astype(np.float32)
    light=(pixels.min(axis=2)>=185).astype(np.float32)
    result=np.zeros(dark.shape,dtype=bool)
    found=[]
    for scale in (1,2):
        template=Image.new("RGBA",(15*scale,23*scale))
        points=[(0,0),(0,17),(4,13),(8,20),(10,18),(7,12),(13,12)]
        ImageDraw.Draw(template).polygon([(x*scale,y*scale) for x,y in points],fill="white",outline="black",width=scale)
        values=np.asarray(template)
        alpha=values[:,:,3]>0
        border=(values[:,:,:3].max(axis=2)<10)&alpha
        white=alpha&~border
        if dark.shape[0]<border.shape[0] or dark.shape[1]<border.shape[1]:
            continue
        hits=fftconvolve(dark,border[::-1,::-1].astype(np.float32),mode="valid")
        fill=fftconvolve(light,white[::-1,::-1].astype(np.float32),mode="valid")
        ys,xs=np.nonzero((hits>=border.sum()*.98)&(fill>=white.sum()*.95))
        for y,x in zip(ys,xs):
            patch=pixels[y:y+alpha.shape[0],x:x+alpha.shape[1]]
            if (patch[white].min(axis=1)>=185).mean()<.95:
                continue
            found.append((int(x),int(y)))
            result[y:y+alpha.shape[0],x:x+alpha.shape[1]]|=alpha
            if len(found)>1:
                return np.zeros(dark.shape,dtype=bool)  # ambiguous: preserve all content
    return result
