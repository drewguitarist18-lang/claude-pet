// Renders ad.html to marketing/claude-pet-ad.mp4: every frame through renderFrame(t), the score through renderAudio(), muxed by ffmpeg.
// Usage: node render.js                    (the film, plus the poster marketing/ad-poster.jpg)
//        node render.js --stills 3.5 12 20 (PNGs of those moments into marketing/stills/, for checking)
// Needs puppeteer-core (NODE_PATH), installed Edge and ffmpeg (FFMPEG or on PATH). Serves the repo itself.
const puppeteer = require("puppeteer-core");
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const FF = process.env.FFMPEG || "ffmpeg", ROOT = path.resolve(__dirname, ".."), FPS = 30, LENGTH = 24, POSTER_AT = 23;
const MEDIA = __dirname, TYPES = { ".html": "text/html", ".js": "text/javascript" };

const server = http.createServer((req, res) => {
  const file = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 600000 });
  const p = await b.newPage();
  await p.setViewport({ width: 1920, height: 1080 });
  p.on("pageerror", (e) => console.log("pageerror", e.message));
  await p.goto(`http://127.0.0.1:${server.address().port}/marketing/ad.html`, { waitUntil: "load" });
  await p.evaluate(() => window.ready);
  const grab = (t, type, q) => p.evaluate(async (t, type, q) => { await renderFrame(t); return document.getElementById("cv").toDataURL(type, q).split(",")[1]; }, t, type, q);
  const args = process.argv.slice(2);

  if (args[0] === "--stills") {
    const dir = path.join(__dirname, "stills"); fs.mkdirSync(dir, { recursive: true });
    for (const t of args.slice(1)) fs.writeFileSync(path.join(dir, `t${(+t).toFixed(2)}.png`), Buffer.from(await grab(+t, "image/png"), "base64"));
    console.log("stills in", dir);
  } else {
    const dir = path.join(__dirname, "frames"), out = path.join(MEDIA, "claude-pet-ad.mp4");
    fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir); fs.mkdirSync(MEDIA, { recursive: true });
    const t0 = Date.now();
    for (let i = 0; i < LENGTH * FPS; i++) {
      fs.writeFileSync(path.join(dir, String(i).padStart(4, "0") + ".jpg"), Buffer.from(await grab(i / FPS, "image/jpeg", .95), "base64"));
      if (i % 90 === 0) console.log("frame", i, ((Date.now() - t0) / 1000).toFixed(0) + "s");
    }
    fs.writeFileSync(path.join(dir, "score.pcm"), Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-framerate", String(FPS), "-i", path.join(dir, "%04d.jpg"),
      "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", path.join(dir, "score.pcm"),
      "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out]);
    fs.writeFileSync(path.join(MEDIA, "ad-poster.jpg"), Buffer.from(await grab(POSTER_AT, "image/jpeg", .86), "base64"));
    fs.rmSync(dir, { recursive: true, force: true });
    console.log("wrote", out, ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); server.close();
})().catch((e) => { console.error(e); process.exit(1); });
