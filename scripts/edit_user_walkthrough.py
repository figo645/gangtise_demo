"""Inspect and edit user-recorded walkthroughs without changing source files."""
import argparse
import json
import subprocess
import asyncio
import re
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/narrated-video-2026-10-14"
SOURCES = Path("/Users/xuchenfei/Documents/咨询/百度云同步盘/视频/AI 洞见智研")
FILES = {
    "home": SOURCES / "主页 录屏2026-10-14 12.58.02.mov",
    "dav": SOURCES / "大V视角所有功能 录屏2026-10-14 13.00.22.mov",
    "fan": SOURCES / "普通投资者视角 录屏2026-10-14 13.07.51.mov",
}


def inspect():
    OUT.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 18)
    for role, source in FILES.items():
        container = av.open(str(source))
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base)
        times = list(range(0, int(duration), 6))
        for start in range(0, len(times), 16):
            sheet = Image.new("RGB", (1600, 4 * 245), "#e8edf3")
            draw = ImageDraw.Draw(sheet)
            for index, seconds in enumerate(times[start:start + 16]):
                container.seek(int(seconds / stream.time_base), stream=stream)
                for frame in container.decode(stream):
                    if float(frame.pts * stream.time_base) >= seconds:
                        image = frame.to_image()
                        image.thumbnail((396, 212))
                        x, y = (index % 4) * 400, (index // 4) * 245
                        sheet.paste(image, (x, y))
                        draw.text((x + 8, y + 215), f"{role} {seconds // 60:02}:{seconds % 60:02}", font=font, fill="#102a46")
                        break
            target = OUT / f"{role}-contact-{start // 16 + 1}.jpg"
            sheet.save(target, quality=88)
            print(target, flush=True)
        container.close()


def media_duration(file):
    with av.open(str(file)) as container:
        return container.duration / av.time_base


def timestamp(seconds, ass=False):
    ms = round(seconds * 1000)
    if ass:
        return f"{ms // 3600000}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000 // 10:02}"
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def ffmpeg(args):
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y', *args], check=True)


def plan():
    return json.loads((OUT / 'edit-plan.json').read_text())


async def voices():
    import edge_tts
    for role, scenes in plan().items():
        for index, scene in enumerate(scenes):
            target = OUT / 'audio' / f'{role}-{index:02}.mp3'
            target.parent.mkdir(exist_ok=True)
            if target.exists() and target.stat().st_size > 1000 and target.with_suffix('.srt').exists():
                continue
            for attempt in range(12):
                try:
                    speech = edge_tts.Communicate(scene[3], 'zh-CN-XiaoxiaoNeural', rate='-8%', pitch='-2Hz', boundary='SentenceBoundary')
                    subtitles = edge_tts.SubMaker()
                    with target.open('wb') as audio:
                        async for chunk in speech.stream():
                            if chunk['type'] == 'audio':
                                audio.write(chunk['data'])
                            elif chunk['type'] == 'SentenceBoundary':
                                subtitles.feed(chunk)
                    target.with_suffix('.srt').write_text(subtitles.get_srt())
                    print(f'voice {role} {index + 1}/{len(scenes)}', flush=True)
                    break
                except Exception as error:
                    print(f'retry {role}-{index:02}: {attempt+1} {type(error).__name__}', flush=True)
                    if attempt == 11:
                        raise
                    await asyncio.sleep(min(attempt+1, 5))


ASS_HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Songti SC,38,&H00FFFFFF,&H00FFFFFF,&H00162B40,&H00162B40,0,0,0,0,100,100,0,0,3,8,0,2,90,90,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def subtitle_cues(text, duration):
    parts = [part for part in re.split(r'(?<=[。！？；，])', text) if part]
    lines = []
    for part in parts:
        if lines and len(lines[-1]) + len(part) <= 28:
            lines[-1] += part
        else:
            while len(part) > 32:
                lines.append(part[:28])
                part = part[28:]
            lines.append(part)
    total = sum(len(line) for line in lines)
    cursor = 0.25
    cues = []
    for line in lines:
        end = cursor + (duration - 0.6) * len(line) / total
        cues.append((cursor, end, line))
        cursor = end
    return cues


def render():
    parts_dir = OUT / 'parts'
    parts_dir.mkdir(exist_ok=True)
    metadata = []
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Songti.ttc', 44)
    small = ImageFont.truetype('/System/Library/Fonts/Supplemental/Songti.ttc', 26)
    role_names = {'home': '产品介绍', 'fan': '普通投资者视角', 'dav': '大V视角'}
    for role, scenes in plan().items():
        cursor = 0
        chapter_cues = []
        chapter_parts = []
        for index, (start, end, title, narration, layout) in enumerate(scenes):
            key = f'{role}-{index:02}'
            audio = OUT / 'audio' / f'{key}.mp3'
            spoken = media_duration(audio)
            duration = max(8, spoken + 1.1)
            cues = subtitle_cues(narration, spoken)
            # Use speech sentence timings when available; fallback remains readable.
            speech_srt = audio.with_suffix('.srt').read_text()
            matches = re.findall(r'(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})\n([^\n]+)', speech_srt)
            if matches:
                cues = []
                for match in matches:
                    a = int(match[0])*3600 + int(match[1])*60 + int(match[2]) + int(match[3])/1000
                    b = int(match[4])*3600 + int(match[5])*60 + int(match[6]) + int(match[7])/1000
                    text = match[8]
                    chunks = [text[i:i+28] for i in range(0, len(text), 28)]
                    for j, chunk in enumerate(chunks):
                        cues.append((a+(b-a)*j/len(chunks), a+(b-a)*(j+1)/len(chunks), chunk))
            ass = OUT / f'{key}.ass'
            ass.write_text(ASS_HEADER + ''.join(f'Dialogue: 0,{timestamp(a, True)},{timestamp(b, True)},Default,,0,0,0,,{text}\n' for a, b, text in cues))
            overlay = Image.new('RGBA', (1920,1080), (0,0,0,0))
            draw = ImageDraw.Draw(overlay)
            if layout == 'mobile':
                draw.text((65,180), '洞见智研', font=small, fill='#8FAFC8')
                draw.text((65,230), role_names[role], font=font, fill='white')
                title_lines = [title[i:i+9] for i in range(0,len(title),9)]
                for n, line in enumerate(title_lines):
                    draw.text((65,330+n*65), line, font=font, fill='#E8CA8B')
                draw.text((65,550), f'{index+1:02} / {len(scenes):02}', font=small, fill='#8FAFC8')
            else:
                draw.rounded_rectangle((20,18,850,80), radius=12, fill=(16,42,70,235))
                draw.text((40,28), role_names[role]+'  ·  '+title, font=small, fill='white')
            label = OUT / f'{key}.png'
            overlay.save(label)
            target = parts_dir / f'{key}.mp4'
            chapter_parts.append(target)
            if not target.exists():
                ratio = duration/(end-start)
                transform = 'crop=1000:1600:992:0,scale=600:960' if layout == 'mobile' else 'scale=1920:960:force_original_aspect_ratio=decrease'
                video_filter = f'[0:v]setpts={ratio:.6f}*(PTS-STARTPTS),{transform},pad=1920:1080:(ow-iw)/2:0:color=0x102A46,fps=25,tpad=stop_mode=clone:stop_duration=2[v];[v][2:v]overlay=0:0,ass={ass}[final]'
                ffmpeg(['-ss', str(start), '-t', str(end-start), '-i', str(FILES[role]), '-i', str(audio), '-loop','1','-i',str(label),
                        '-filter_complex',video_filter,'-map','[final]','-map','1:a','-af','apad,alimiter=limit=0.95',
                        '-t', str(duration), '-c:v','libx264','-preset','veryfast','-crf','21','-threads','4',
                        '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000','-ac','2','-movflags','+faststart',str(target)])
            for a,b,text in cues:
                chapter_cues.append((cursor+a,cursor+b,text))
            metadata.append({'role':role,'title':title,'source_start':start,'source_end':end,'start':cursor,'duration':duration,'narration':narration})
            cursor += duration
            print(f'rendered {key}: {duration:.1f}s', flush=True)
        concat_file = OUT / f'{role}-concat.txt'
        concat_file.write_text(''.join(f"file '{file}'\n" for file in chapter_parts))
        ffmpeg(['-f','concat','-safe','0','-i',str(concat_file),'-c','copy','-movflags','+faststart',str(OUT/f'{role}-narrated.mp4')])
        (OUT/f'{role}-subtitles.srt').write_text(''.join(f'{i+1}\n{timestamp(a)} --> {timestamp(b)}\n{text}\n\n' for i,(a,b,text) in enumerate(chapter_cues)))
        entries = [entry for entry in metadata if entry['role']==role]
        (OUT/f'{role}-script.md').write_text('# '+role_names[role]+'讲解脚本\n\n声音：Xiaoxiao中文合成女声，语速-8%，音调-2Hz。\n\n'+''.join(f"## {timestamp(e['start'])[:8]} {e['title']}\n\n{e['narration']}\n\n" for e in entries))
    (OUT/'timeline.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    concat_file = OUT/'all-concat.txt'
    concat_file.write_text(''.join(f"file '{OUT / (role+'-narrated.mp4')}'\n" for role in ['home','fan','dav']))
    ffmpeg(['-f','concat','-safe','0','-i',str(concat_file),'-c','copy','-movflags','+faststart',str(OUT/'洞见智研-完整讲解.mp4')])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inspect', 'voice', 'render'], nargs='?', default='inspect')
    args = parser.parse_args()
    if args.mode == 'voice':
        asyncio.run(voices())
    elif args.mode == 'render':
        render()
    else:
        inspect()
