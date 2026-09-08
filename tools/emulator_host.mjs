// Dedicated local openMSX instance. No other emulator process is contacted.
import {spawn} from 'node:child_process';
import {createServer as netServer} from 'node:net';
import {createServer as httpServer} from 'node:http';
import {appendFileSync, existsSync, mkdirSync} from 'node:fs';
import {delimiter, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const work = join(root, 'work');
const installedDirectory = process.env.OPENMSX_HOME || join(process.env.ProgramFiles || 'C:\\Program Files', 'openMSX');
const executable = process.env.OPENMSX_EXE || join(installedDirectory, 'openmsx.exe');
const pipeName = 'magical-happy-rally-' + process.pid;
const port = Number(process.env.OPENMSX_PORT || 18796);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('OPENMSX_PORT must be an integer from 1024 to 65535.');
const extra = process.argv.slice(2);
if (!existsSync(executable)) throw new Error('Set OPENMSX_EXE to your existing openmsx.exe.');
if (!extra.length) {
  const rom = join(root, 'outputs', 'MAGICAL_HAPPY_RALLY-v0.4.rom');
  if (!existsSync(rom)) throw new Error('Build MAGICAL_HAPPY_RALLY-v0.4.rom with BUILD.cmd first.');
  extra.push('-cart', rom, '-romtype', 'ASCII8');
}
mkdirSync(work, {recursive: true});
let socket, child, buffer = '', pending = [], stopping = false;
const encode = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const decode = value => value.replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"').replaceAll('&apos;', "'").replaceAll('&amp;', '&');
function rejectPending(error) {
  for (const request of pending.splice(0)) request.reject(error);
}
function command(value) {
  return new Promise((resolveRequest, reject) => {
    if (!socket || socket.destroyed) { reject(new Error('Emulator is not connected yet.')); return; }
    pending.push({resolve: resolveRequest, reject});
    socket.write('<command>' + encode(value) + '</command>\n');
  });
}
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  rejectPending(new Error('This emulator instance has stopped.'));
  socket?.destroy();
  if (child && child.exitCode === null) child.kill();
  pipe.close();
  server.close();
  process.exitCode = code;
}
const pipe = netServer(connection => {
  if (socket) { connection.destroy(); return; }
  socket = connection;
  socket.setEncoding('utf8');
  socket.on('data', data => {
    appendFileSync(join(work, 'emulator-xml.log'), data);
    buffer += data;
    let match;
    while ((match = buffer.match(/<reply\s+result="(ok|nok)">([\s\S]*?)<\/reply>/))) {
      buffer = buffer.slice(match.index + match[0].length);
      const request = pending.shift();
      if (request) (match[1] === 'ok' ? request.resolve : request.reject)(decode(match[2]));
    }
    if (buffer.length > 1048576) buffer = buffer.slice(-65536);
  });
  socket.on('error', error => rejectPending(error));
  socket.on('close', () => rejectPending(new Error('Emulator control pipe closed.')));
  socket.write('<openmsx-control>\n');
  console.log('CONNECTED: MAGICAL HAPPY RALLY control at http://127.0.0.1:' + port);
});
const server = httpServer(async (request, response) => {
  if (request.headers.origin) { response.writeHead(403); response.end('Local development client only.'); return; }
  if (request.method === 'GET' && request.url === '/health') {
    response.writeHead(200, {'Content-Type': 'application/json'});
    response.end(JSON.stringify({project: 'MAGICAL HAPPY RALLY', port, connected: !!socket && !socket.destroyed, pid: child?.pid}));
    return;
  }
  if (request.method !== 'POST') { response.writeHead(405); response.end(); return; }
  let body = '';
  try {
    for await (const chunk of request) {
      body += chunk;
      if (body.length > 65536) throw new Error('Command exceeds 64 KiB.');
    }
    const result = await command(body);
    response.writeHead(200, {'Content-Type': 'text/plain; charset=utf-8'});
    response.end(result);
  } catch (error) {
    response.writeHead(500, {'Content-Type': 'text/plain; charset=utf-8'});
    response.end(String(error));
  }
});
server.on('error', error => { console.error(error.message); stop(1); });
pipe.on('error', error => { console.error(error.message); stop(1); });
// Reserve the project's port before starting any GUI process.
server.listen(port, '127.0.0.1', () => {
  pipe.listen('\\\\.\\pipe\\' + pipeName, () => {
    child = spawn(executable, ['-control', 'pipe:' + pipeName, '-machine', 'Panasonic_FS-A1ST',
      '-ext', 'gfx9000', '-script', join(root, 'tools', 'emulator_bridge.tcl'), ...extra],
      {cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], env: {
        ...process.env,
        OPENMSX_SYSTEM_DATA: process.env.OPENMSX_SYSTEM_DATA || join(installedDirectory, 'share'),
        PATH: installedDirectory + delimiter + (process.env.PATH || ''),
      }});
    child.stdout.on('data', data => process.stdout.write(data));
    child.stderr.on('data', data => process.stderr.write(data));
    child.on('error', error => { console.error(error.message); stop(1); });
    child.on('exit', code => stop(code || 0));
  });
});
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
