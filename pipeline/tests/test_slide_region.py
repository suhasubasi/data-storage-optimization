"""Synthetic comparison fixtures stay in temporary test folders."""
import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image,ImageDraw

from dso_pipeline import unique_slides as U,video
from dso_pipeline.slide_region import presentation_box,presentation_image


def page(text="Radio bandwidth 100 MHz",cursor=None):
    image=Image.new("RGB",(800,450),"white")
    draw=ImageDraw.Draw(image)
    draw.text((35,40),text,fill="black",font_size=32)
    draw.rectangle((50,160,200,280),outline="navy",width=4)
    if cursor:
        x,y=cursor
        draw.polygon([(x,y),(x,y+17),(x+4,y+13),(x+8,y+20),(x+10,y+18),(x+7,y+12),(x+13,y+12)],fill="white",outline="black")
    return image


def meeting(slide,seed):
    image=Image.new("RGB",(920,600),"black")
    image.paste(slide,(0,75))
    webcam=np.random.default_rng(seed).integers(0,255,(100,120,3),dtype=np.uint8)
    image.paste(Image.fromarray(webcam),(800,0))
    return image


def frames_on_disk(tmp_path,images):
    frames=[]
    for i,image in enumerate(images):
        path=tmp_path/f"f{i+1}.webp"
        image.save(path,"WEBP",lossless=True)
        frames.append({"id":f"f{i+1}","path":path.name,"t_start":i,"t_end":i+1,
                       "bytes":path.stat().st_size,"phash":"0"*16,"matched_slide":None})
    return frames


def test_presentation_panel_excludes_moving_camera():
    a,b=meeting(page(),1),meeting(page(),2)
    assert presentation_box(a)==(0,75,800,525)
    assert presentation_image(a).tobytes()==presentation_image(b).tobytes()==page().tobytes()


def test_sixty_camera_frames_reuse_one_slide_with_complete_timeline(tmp_path):
    frames=frames_on_disk(tmp_path,[meeting(page(),i) for i in range(60)])
    result=U.apply(frames,tmp_path,U.config({}))
    assert result["info"]["source_frame_count"]==60
    assert result["info"]["unique_slide_count"]==1
    assert result["frames"][0]["t_start"]==0 and result["frames"][0]["t_end"]==60
    assert len(result["frames"][0]["source_frames"])==60


def test_sampler_does_not_save_webcam_only_changes(monkeypatch,tmp_path):
    images=[meeting(page(),i) for i in range(4)]
    process=SimpleNamespace(stdout=io.BytesIO(b"".join(image.tobytes() for image in images)),
                            stderr=io.BytesIO(),wait=lambda:0)
    monkeypatch.setattr(video.subprocess,"Popen",lambda *args,**kwargs:process)
    extracted=list(video._key_frames(tmp_path/"input.mp4",images[0].size,1,12,8,.01,24))
    assert len(extracted)==1 and extracted[0][0]==0
    assert extracted[0][1].size==(800,450)


def test_cursor_movement_does_not_create_new_slide(tmp_path):
    frames=frames_on_disk(tmp_path,[meeting(page(cursor=(300+i*25,350)),i) for i in range(6)])
    result=U.apply(frames,tmp_path,U.config({}))
    assert result["info"]["unique_slide_count"]==1


def test_real_text_change_and_return_to_slide_keep_their_times(tmp_path):
    frames=frames_on_disk(tmp_path,[meeting(page(),1),meeting(page("Radio bandwidth 110 MHz"),2),meeting(page(),3)])
    result=U.apply(frames,tmp_path,U.config({}))
    assert result["info"]["unique_slide_count"]==2
    assert [f["slide"] for f in result["frames"]]==[1,2,1]
    assert [(f["t_start"],f["t_end"]) for f in result["frames"]]==[(0,1),(1,2),(2,3)]


def test_cursor_mask_cannot_hide_a_changed_number(tmp_path):
    a=meeting(page(cursor=(300,350)),1)
    b=meeting(page("Radio bandwidth 110 MHz",cursor=(500,350)),2)
    result=U.apply(frames_on_disk(tmp_path,[a,b]),tmp_path,U.config({}))
    assert result["info"]["unique_slide_count"]==2


def test_older_postpass_can_be_upgraded_without_changing_transcript(tmp_path):
    from dso_pipeline import postpass
    from test_unique_slides import _manifest
    import json
    base=tmp_path/"derived"/"a_t"
    base.mkdir(parents=True)
    frames=frames_on_disk(base,[meeting(page(),1),meeting(page(),2)])
    derived=[{"path":f["path"],"bytes":f["bytes"],"kind":"frame"} for f in frames]
    _manifest(base,frames,derived)
    first=postpass.run_unique_slides("a_t",base)
    path=base/"manifest.json"
    manifest=json.loads(path.read_text())
    segments=manifest["segments"]
    manifest["pipeline"]["unique_slides"]["method"]="older slide algorithm"
    path.write_text(json.dumps(manifest))
    postpass.run_unique_slides("a_t",base)
    after=json.loads(path.read_text())
    assert after["segments"]==segments
    assert after["pipeline"]["unique_slides"]["method"]==U.METHOD
    assert first["unique_slides"]==1
    with pytest.raises(postpass.PostPassError):
        postpass.run_unique_slides("a_t",base)


def test_uncertain_layout_keeps_full_frame_and_manual_crop_is_validated():
    dark=Image.new("RGB",(800,450),"#222222")
    ImageDraw.Draw(dark).rectangle((70,70,730,390),fill="white")
    assert presentation_box(dark) is None
    assert presentation_image(dark).size==dark.size
    assert presentation_image(dark,[0,.1,.8,.9]).size==(640,360)
    with pytest.raises(ValueError):
        presentation_box(dark,[0,0,1.2,1])
