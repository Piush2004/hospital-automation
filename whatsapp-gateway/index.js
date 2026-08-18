/**
 * Unofficial WhatsApp Web bridge (Baileys) -> the same orchestrator every
 * other channel uses, via a plain HTTP webhook. See README.md: this is
 * ToS-grey-area and can get a number banned - fine for local prototyping,
 * swap to the official Meta WhatsApp Cloud API before any real deployment.
 *
 * Two message flows:
 *   1. Inbound: a WhatsApp message arrives -> POST to the backend webhook
 *      -> backend runs one orchestrator turn and returns the reply in the
 *      HTTP response -> we send that reply back over the same Baileys
 *      socket. Synchronous request/response, no separate push needed.
 *   2. Outbound/proactive: the backend wants to nudge a patient who isn't
 *      actively mid-message (payment confirmed, report ready) -> it POSTs
 *      to this gateway's own /send endpoint (see notifications.py's
 *      whatsapp branch) -> we relay it over the same socket.
 *
 * First run: scan the printed QR code with the WhatsApp app on the phone
 * you're using for this (use a throwaway/test number, not your primary
 * one, given the ban risk noted above). Session credentials are cached in
 * ./auth_info (gitignored) so subsequent runs don't need re-scanning.
 */

require("dotenv").config();

const http = require("http");
const path = require("path");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const qrcodeTerminal = require("qrcode-terminal");

const WEBHOOK_URL = process.env.WEBHOOK_URL || "http://localhost:8000/webhook/whatsapp";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "change-me";
const PORT = Number(process.env.PORT || 3001);
const AUTH_DIR = path.join(__dirname, "auth_info");

const logger = pino({ level: "warn" });

let currentSocket = null;
// makeWASocket() returns a socket object synchronously, well before the
// connection is actually authenticated - `currentSocket` alone isn't a
// reliable "can I send" signal (calling sendMessage before "open" fails
// deep inside Baileys with an unhelpful error). Track the real state.
let isConnected = false;

function extractText(message) {
  if (!message) return null;
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    null
  );
}

function jidToPhone(jid) {
  // "919810000001@s.whatsapp.net" -> "+919810000001"
  const digits = jid.split("@")[0].split(":")[0];
  return `+${digits}`;
}

function phoneToJid(phone) {
  const digits = phone.replace(/[^0-9]/g, "");
  return `${digits}@s.whatsapp.net`;
}

async function forwardToBackend(phone, text) {
  const resp = await fetch(WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, message: text, secret: WEBHOOK_SECRET }),
  });
  if (!resp.ok) {
    throw new Error(`Webhook responded ${resp.status}: ${await resp.text()}`);
  }
  const data = await resp.json();
  return data.reply;
}

async function startWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false, // we handle QR display ourselves for a clearer message
  });
  currentSocket = sock;

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\nScan this QR code with WhatsApp (Linked Devices -> Link a Device):\n");
      qrcodeTerminal.generate(qr, { small: true });
    }

    if (connection === "close") {
      isConnected = false;
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`Connection closed (status ${statusCode}). Reconnecting: ${shouldReconnect}`);
      if (shouldReconnect) {
        startWhatsApp().catch((err) => console.error("Reconnect failed:", err));
      } else {
        console.log("Logged out - delete ./auth_info and restart to re-pair.");
      }
    } else if (connection === "open") {
      isConnected = true;
      console.log("WhatsApp connection open. Ready to relay messages.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (msg.key.fromMe) continue;
      if (msg.key.remoteJid?.endsWith("@g.us")) continue; // skip group chats

      const text = extractText(msg.message);
      if (!text) continue;

      const phone = jidToPhone(msg.key.remoteJid);
      console.log(`[in]  ${phone}: ${text}`);

      try {
        const reply = await forwardToBackend(phone, text);
        if (reply) {
          await sock.sendMessage(msg.key.remoteJid, { text: reply });
          console.log(`[out] ${phone}: ${reply.slice(0, 80)}${reply.length > 80 ? "..." : ""}`);
        }
      } catch (err) {
        console.error(`Failed to handle message from ${phone}:`, err.message);
      }
    }
  });

  return sock;
}

function startLocalServer() {
  const server = http.createServer((req, res) => {
    if (req.method !== "POST" || req.url !== "/send") {
      res.writeHead(404).end();
      return;
    }

    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", async () => {
      try {
        const { phone, message } = JSON.parse(body);
        if (!phone || !message) {
          res.writeHead(400).end(JSON.stringify({ error: "phone and message are required" }));
          return;
        }
        if (!currentSocket || !isConnected) {
          res.writeHead(503).end(JSON.stringify({ error: "WhatsApp not connected yet" }));
          return;
        }
        await currentSocket.sendMessage(phoneToJid(phone), { text: message });
        res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({ ok: true }));
      } catch (err) {
        console.error("POST /send failed:", err.message);
        res.writeHead(500).end(JSON.stringify({ error: err.message }));
      }
    });
  });

  server.listen(PORT, () => {
    console.log(`WhatsApp gateway HTTP server listening on :${PORT} (POST /send for proactive pushes)`);
  });
}

startLocalServer();
startWhatsApp().catch((err) => {
  console.error("Failed to start WhatsApp connection:", err);
  console.error("The local /send HTTP server is still up, but nothing will actually be delivered.");
});
