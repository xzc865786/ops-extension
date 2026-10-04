// Test-only server for trying the manual from a Hyper-V VM.
// Serves frontend/manual at /docs/ with the same headers as frontend/nginx.conf, and forwards
// /v1/* to https://api.tysy.top so "读取可用模型" works. Nothing is logged except method, path and status.
// Run:  node output/vm-test/manual-server.mjs   (listens on 0.0.0.0:18089)
import {createServer} from 'node:http';
import {request} from 'node:https';
import {readFile, stat} from 'node:fs/promises';
import {extname, join, normalize, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const PORT = Number(process.env.PORT || 18089);
const ROOT = resolve(fileURLToPath(new URL('../../frontend/manual/', import.meta.url)));
const UPSTREAM = 'api.tysy.top';
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
  '.cmd': 'application/octet-stream', '.msi': 'application/octet-stream',
};
const DOC_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cache-Control': 'no-cache',
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'; frame-ancestors 'none'",
};

function proxy(req, res) {
  const headers = {...req.headers, host: UPSTREAM};
  delete headers.origin;
  delete headers.referer;
  const upstream = request({host: UPSTREAM, port: 443, method: req.method, path: req.url, headers, servername: UPSTREAM}, response => {
    res.writeHead(response.statusCode, response.headers);
    response.pipe(res);
    console.log(`${req.method} ${req.url.split('?')[0]} -> ${response.statusCode}`);
  });
  upstream.on('error', error => {
    res.writeHead(502, {'Content-Type': 'text/plain; charset=utf-8'});
    res.end(`upstream error: ${error.message}`);
    console.log(`${req.method} ${req.url} -> 502 ${error.message}`);
  });
  req.pipe(upstream);
}

async function serveDoc(req, res, pathname) {
  let relative = decodeURIComponent(pathname.slice('/docs/'.length)) || 'index.html';
  if (relative.endsWith('/')) relative += 'index.html';
  const file = normalize(join(ROOT, relative));
  if (file !== ROOT && !file.startsWith(ROOT + sep)) return send(res, 404, 'not found');
  try {
    const info = await stat(file);
    if (info.isDirectory()) return send(res, 404, 'not found');
    const body = await readFile(file);
    res.writeHead(200, {...DOC_HEADERS, 'Content-Type': TYPES[extname(file).toLowerCase()] || 'application/octet-stream', 'Content-Length': body.length});
    res.end(req.method === 'HEAD' ? undefined : body);
    console.log(`${req.method} ${pathname} -> 200`);
  } catch {
    send(res, 404, 'not found');
    console.log(`${req.method} ${pathname} -> 404`);
  }
}

function send(res, status, text, headers = {}) {
  res.writeHead(status, {'Content-Type': 'text/plain; charset=utf-8', ...headers});
  res.end(text);
}

createServer((req, res) => {
  const {pathname} = new URL(req.url, 'http://localhost');
  if (pathname === '/' || pathname === '/docs') return send(res, 308, '', {Location: '/docs/'});
  if (pathname.startsWith('/v1/')) return proxy(req, res);
  if (pathname.startsWith('/docs/')) return serveDoc(req, res, pathname);
  if (pathname === '/vm/setup-ssh.ps1') {
    // Only this one file from output/vm-test is exposed: the VM fetches it with `irm ... | iex`.
    return readFile(new URL('./setup-ssh.ps1', import.meta.url)).then(body => {
      res.writeHead(200, {'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store'});
      res.end(body);
      console.log(`GET ${pathname} -> 200`);
    }, () => send(res, 404, 'not found'));
  }
  send(res, 404, 'not found');
}).listen(PORT, '0.0.0.0', () => {
  console.log(`Manual test server: http://0.0.0.0:${PORT}/docs/  (serving ${ROOT})`);
});
