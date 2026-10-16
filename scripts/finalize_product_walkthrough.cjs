// Trim initial loading screens and align narration with the final video.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const output = path.resolve(process.env.DEMO_OUTPUT || 'reports/product-video-2026-10-14');
const ffmpeg = process.env.DEMO_FFMPEG || '/private/tmp/gangtise-video-browsers/ffmpeg-1011/ffmpeg-mac';
function time(seconds, separator = ',') {
  const milliseconds = Math.max(0, Math.round(seconds * 1000));
  return `${String(Math.floor(milliseconds / 3600000)).padStart(2, '0')}:${String(Math.floor(milliseconds / 60000) % 60).padStart(2, '0')}:${String(Math.floor(milliseconds / 1000) % 60).padStart(2, '0')}${separator}${String(milliseconds % 1000).padStart(3, '0')}`;
}

for (const role of ['fan', 'dav']) {
  const scenes = JSON.parse(fs.readFileSync(path.join(output, `${role}-timeline.json`), 'utf8'));
  if (!scenes.length || scenes.some(scene => scene.status !== 'recorded')) throw new Error(`Incomplete recording: ${role}`);
  const source = path.join(output, `${role}-walkthrough.webm`);
  const metadata = spawnSync(ffmpeg, ['-hide_banner', '-i', source], { encoding: 'utf8' });
  const match = (metadata.stderr || '').match(/Duration: (\d+):(\d+):(\d+\.\d+)/);
  if (!match) throw new Error(`Cannot read video duration: ${role}`);
  const mediaDuration = Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
  // Browser recording and wall-clock timing may drift during heavy page loads.
  const scale = mediaDuration / scenes[scenes.length - 1].end;
  const offset = scenes[0].start * scale;
  const duration = mediaDuration - offset;
  const result = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y',
    '-i', source, '-ss', String(offset), '-t', String(duration),
    '-an', '-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '8', '-b:v', '1400k',
    path.join(output, `${role}-demo.webm`)], { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Video processing failed: ${role}`);
  const timeline = scenes.map(scene => ({ ...scene, start: scene.start * scale - offset, end: scene.end * scale - offset }));
  for (const extension of ['srt', 'vtt']) {
    const cues = timeline.map((scene, index) => `${index + 1}\n${time(scene.start, extension === 'vtt' ? '.' : ',')} --> ${time(scene.end, extension === 'vtt' ? '.' : ',')}\n${scene.narration}\n`).join('\n');
    fs.writeFileSync(path.join(output, `${role}-demo.${extension}`), (extension === 'vtt' ? 'WEBVTT\n\n' : '') + cues);
  }
  fs.writeFileSync(path.join(output, `${role}-script.md`),
    `# ${role === 'fan' ? '粉丝' : '大V'}视角讲解脚本\n\n配套视频：${role}-demo.webm，时长约 ${Math.round(duration)} 秒。镜头时间为近似值。\n\n本机真实页面录屏，无配音；旁白稿与字幕单独提供。演示没有保存草稿、发布内容或修改配置。行情缺失按实际页面呈现。\n\n` +
    timeline.map(scene => `## ${time(scene.start).slice(0, 8)} — ${time(scene.end).slice(0, 8)} ${scene.title}\n\n${scene.narration}\n`).join('\n'));
  console.log(`${role}: ${Math.round(duration)} seconds, aligned script and subtitles generated`);
}

fs.writeFileSync(path.join(output, 'preview.html'), `<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>洞见智研 · 双角色产品演示</title>
<style>body{margin:0;background:#f2f6fa;color:#102a46;font:16px/1.7 sans-serif}main{max-width:1100px;margin:40px auto;padding:0 20px}h1{font-size:28px}section{background:white;border-radius:16px;padding:24px;margin:24px 0}video{display:block;width:100%;max-height:75vh;background:#102a46;border-radius:10px}a{color:#145b99;margin-right:20px}p{color:#53677c}.fan{max-width:430px;margin:auto}</style>
<main><h1>洞见智研 · 粉丝与大V产品演示</h1><p>真实页面录屏，暂无配音。可开启播放器字幕，按旁白稿讲解。</p>
${['fan', 'dav'].map(role => `<section><h2>${role === 'fan' ? '粉丝视角' : '大V视角'}</h2><video class="${role}" controls preload="metadata" poster="${role === 'fan' ? 'fan-review.png' : 'dav-overview.png'}"><source src="${role}-demo.webm" type="video/webm"><track kind="subtitles" label="中文讲解" srclang="zh" src="${role}-demo.vtt" default></video><p><a href="${role}-script.md">讲解脚本</a><a href="${role}-demo.srt">SRT字幕</a></p></section>`).join('')}
</main></html>`);
