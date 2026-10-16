// Record authenticated, read-only product walkthroughs from the running app.
const { chromium } = require('/Users/xuchenfei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const baseURL = process.env.DEMO_BASE_URL || 'http://127.0.0.1:5001';
const output = path.resolve(process.env.DEMO_OUTPUT || 'reports/product-video-2026-10-14');
const inspect = process.argv.includes('--inspect');

const tours = {
  fan: [
    ['粉丝视角 · 每日研究入口', '打开洞见智研，先看所属大V的最新洞见，再浏览行业、市场和公开新闻。页面把研究内容和市场信息放在同一个入口。', 'home'],
    ['洞见笔记 · 找到关心的研究', '点击洞见，可以按主题、股票名称或代码查询历史内容。常规笔记和订阅专享分别标记，阅读范围由每篇笔记决定。', 'review'],
    ['九宫格洞见 · 一页看多只股票', '打开九宫格笔记，可以同时查看多只股票的名称、代码、行情和作者简述。没有填写理由的格子，不会额外显示占位提示。', 'article'],
    ['自选股 · 跟踪自己的关注标的', '自选股页面集中提供个股入口、ETF、热门行业、市场一览和宏观经济。输入股票代码即可进入详情，再决定是否加入自选。', 'market'],
    ['ETF · 按类别浏览', 'ETF 按宽基、行业主题、跨境、债券和商品分类。请结合行情日期阅读价格和涨跌幅，日线行情不等于盘中实时行情。', 'etf'],
    ['我的 · 所属大V和账户管理', '在我的页面，可以确认所属大V、租户关系和账号身份。小金智能体等入口取决于平台的实际功能开关，本次账户未开放小金入口。', 'profile'],
  ],
  dav: [
    ['大V视角 · 研究生产工作台', '大V工作台把洞见创作、数据源、预测模型和粉丝经营组织在左侧菜单中。今天重点看从研究输入到内容预览的工作流程。', 'overview'],
    ['洞见发布台 · 三种内容形态', '洞见支持用户文案或文件输入、系统午晚定时报告，以及九宫格个股展示。先选择内容形态，再决定常规笔记或订阅专享范围。', 'review'],
    ['创建九宫格 · 任意搜索股票', '发布新洞见后，选择九宫格个股展示。可以搜索任意合法证券，不受大V已有自选股限制，每篇最多选择九支股票。', 'grid'],
    ['填写理由 · 每只股票独立编辑', '选择股票后，格子展示行情。需要表达观点时，点击填写理由即可编辑；理由可以留空。生成预览后应审核，再正式发布。本次演示不发布。', 'reason'],
    ['预测模型 · 查看计算流程', '预测模型页面展示信号合成、涨幅约束、波动率控制和置信度处理。这里演示算法流程和节点检查器，页面示例输出不是个股投资结论。', 'forecast-model'],
    ['ETF 数据源 · 查看真实行情状态', 'ETF 数据源展示完整目录、分类、最新价、涨跌幅、行情日期和状态，复用 Gangtise 日线接口。缺失数据会明确标记，不会用模拟报价补齐。', 'lake-etf'],
    ['午晚财经播报 · 系统内容生产', '午晚财经播报由系统任务按配置运行，大V可以查看计划和执行记录。自动内容、手写内容和九宫格最终都通过洞见笔记触达粉丝。', 'daily-broadcast'],
    ['已发布洞见 · 回看内容', '已发布洞见集中管理历史笔记。粉丝阅读端与大V发布端共用业务链路。本次录屏仅展示页面和临时输入，没有保存草稿、发布内容或修改配置。', 'published'],
  ],
};

function subtitleTime(seconds) {
  const ms = Math.round(seconds * 1000);
  return `${String(Math.floor(ms / 3600000)).padStart(2,'0')}:${String(Math.floor(ms / 60000) % 60).padStart(2,'0')}:${String(Math.floor(ms / 1000) % 60).padStart(2,'0')},${String(ms % 1000).padStart(3,'0')}`;
}

async function recordTour(browser, role) {
  const context = await browser.newContext({
    viewport: role === 'fan' ? {width:430,height:900} : {width:1440,height:900},
    recordVideo: {dir:output, size:role === 'fan' ? {width:430,height:900} : {width:1440,height:900}},
    locale:'zh-CN', timezoneId:'Asia/Shanghai',
  });
  const timeline = [];
  let page;
  try {
    await login(context, role === 'fan' ? '投研达人_小陈' : '财经老王', process.env.DEMO_PASSWORD || 'demo123');
    page = await context.newPage();
    const began = Date.now();
    page.on('dialog', dialog => dialog.dismiss());
    await page.goto(`${baseURL}/${role === 'fan' ? 'h5?tenant=laowang' : 'kol-workbench?tenant=laowang'}`, {waitUntil:'domcontentloaded',timeout:90000});
    await page.waitForTimeout(4000);
    const notice = page.getByRole('button',{name:'我知道了',exact:true});
    if (await notice.isVisible()) await notice.click();
    for (const [title, narration, action] of tours[role]) {
      const scene = {title,narration,start:(Date.now()-began)/1000, status:'recorded'};
      await page.evaluate(({title,role}) => {
        let label = document.getElementById('walkthrough-caption');
        if (!label) {
          label = document.createElement('div'); label.id = 'walkthrough-caption';
          label.style.cssText = `position:fixed;z-index:2147483647;pointer-events:none;left:12px;right:12px;bottom:${role==='fan'?'75px':'16px'};padding:12px 16px;background:rgba(16,42,70,.95);color:#fff;border-radius:10px;font:600 ${role==='fan'?'15':'20'}px/1.5 sans-serif;box-shadow:0 3px 18px #0002;`;
          document.body.append(label);
        }
        label.textContent = title;
      },{title,role});
      try {
        if (role === 'fan') {
          if (action === 'review') await page.locator('#nav-review').click();
          if (action === 'article') await page.locator('.review-article-card').first().click();
          if (action === 'market') { await page.locator('#nav-market').click(); }
          if (action === 'etf') await page.locator('#market-etf-tab').click();
          if (action === 'profile') await page.locator('#nav-profile').click();
        } else if (action === 'grid') {
          await page.getByRole('button',{name:'发布新洞见',exact:true}).click();
          await page.getByRole('radio',{name:/九宫格个股展示/}).click();
          await page.locator('#kw-review-title-input').fill('今日个股观察（演示预览）');
          await page.locator('#kw-stock-grid-search').fill('600519');
          await page.waitForTimeout(1800);
          const choice = page.locator('button[onclick="kwToggleStockGridSelection(\'600519\')"]');
          await choice.first().waitFor({timeout:15000});
          await choice.first().click();
        } else if (action === 'reason') {
          const reason = page.locator('#kw-stock-grid-reason-tag-600519');
          await reason.click();
          await page.locator('.stock-grid-reason-input').fill('关注经营表现与估值变化，结合后续披露持续跟踪。');
          await page.locator('#kw-stock-grid-reason-tag-600519').click();
        } else {
          await page.locator(`.admin-nav-item[data-section="${action}"]`).click();
        }
        await page.waitForTimeout(action === 'lake-etf' ? 7000 : 2000);
        if (action === 'article') await page.evaluate(() => window.scrollTo({top:240,behavior:'smooth'}));
        if (action === 'grid' || action === 'reason') await page.locator('#kw-review-title-input').scrollIntoViewIfNeeded();
      } catch (error) { scene.status = 'partial'; scene.error = error.message; console.log(`${role}/${action}: ${error.message.split('\n')[0]}`); }
      await page.waitForTimeout(11000);
      await page.screenshot({path:path.join(output,`${role}-${action}.png`)});
      scene.end = (Date.now()-began)/1000;
      timeline.push(scene);
      console.log(`${role}: ${title} (${Math.round(scene.start)}-${Math.round(scene.end)}s) ${scene.status}`);
    }
  } finally {
    await context.close();
    if (page) await page.video().saveAs(path.join(output,`${role}-walkthrough.webm`));
    fs.writeFileSync(path.join(output,`${role}-timeline.json`),JSON.stringify(timeline,null,2));
    fs.writeFileSync(path.join(output,`${role}-narration.srt`),timeline.map((s,i) => `${i+1}\n${subtitleTime(s.start)} --> ${subtitleTime(s.end)}\n${s.narration}\n`).join('\n'));
    fs.writeFileSync(path.join(output,`${role}-script.md`),`# ${role === 'fan'?'粉丝':'大V'}视角视频讲解脚本\n\n本机真实页面录屏。旁白稿单独提供，视频没有配音。录制仅展示与临时输入，不保存或发布。\n\n`+timeline.map(s => `## ${subtitleTime(s.start).slice(0,8)} ${s.title}\n\n${s.narration}\n\n${s.status === 'partial'?'录制说明：该镜头部分操作未成功，请结合实际页面讲解。\n\n':''}`).join(''));
  }
}

async function login(context, username, password) {
  const response = await context.request.post(`${baseURL}/api/h5/login/password`, {
    data: { username, password }, timeout: 60000,
  });
  const data = await response.json();
  if (!response.ok() || data.ok === false) throw new Error(`Login failed for ${username}: HTTP ${response.status()}`);
  return data.current_profile;
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    if (!inspect) {
      for (const role of ['fan','dav']) await recordTour(browser,role);
      return;
    }
    for (const role of ['fan', 'dav']) {
      const context = await browser.newContext({
        viewport: role === 'fan' ? { width: 430, height: 900 } : { width: 1440, height: 900 },
        locale: 'zh-CN', timezoneId: 'Asia/Shanghai',
      });
      try {
        await login(context, role === 'fan' ? '投研达人_小陈' : '财经老王', process.env.DEMO_PASSWORD || 'demo123');
        const page = await context.newPage();
        await page.goto(`${baseURL}/${role === 'fan' ? 'h5?tenant=laowang' : 'kol-workbench?tenant=laowang'}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
        await page.waitForTimeout(6000);
        const notice = page.getByRole('button', { name: '我知道了', exact: true });
        if (await notice.isVisible()) await notice.click();
        const details = await page.evaluate(() => ({
          title: document.title, url: location.href,
          body: document.body.innerText.slice(0, 14000),
          buttons: [...document.querySelectorAll('button,[onclick]')].filter(el => el.getBoundingClientRect().width && el.getBoundingClientRect().height).slice(0, 100).map(el => ({text:el.textContent.trim().slice(0, 80),id:el.id,onclick:el.getAttribute('onclick')})),
          functions: Object.fromEntries(['switchTab', 'showWorkbenchSection', 'openWatchlistDetailFromCard'].map(name => [name, typeof window[name]])),
        }));
        fs.writeFileSync(path.join(output, `${role}-inspection.json`), JSON.stringify(details, null, 2));
        await page.screenshot({ path: path.join(output, `${role}-inspection.png`) });
        console.log(JSON.stringify({role, ...details}));
        const sections = role === 'fan' ? ['review', 'market', 'profile'] : ['review', 'forecast-model', 'lake-etf'];
        for (const section of sections) {
          await page.evaluate(({role, section}) => role === 'fan' ? switchTab(section) : showWorkbenchSection(section), {role, section});
          await page.waitForTimeout(section === 'lake-etf' ? 12000 : 2500);
          const body = await page.locator('body').innerText();
          fs.writeFileSync(path.join(output, `${role}-${section}-inspection.txt`), body);
          await page.screenshot({path: path.join(output, `${role}-${section}-inspection.png`)});
          console.log(JSON.stringify({role, section, body: body.slice(-8000)}));
          if (role === 'dav' && section === 'review') {
            await page.getByRole('button', {name:'发布新洞见', exact:true}).click();
            await page.waitForTimeout(1000);
            console.log(JSON.stringify({role, section:'create', body:(await page.locator('body').innerText()).slice(-9000)}));
            await page.screenshot({path:path.join(output,'dav-create-inspection.png')});
          }
        }
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
