/* Poezenspel — twee spellen uit twee tekeningen, in de browser.
 *
 * Alles wat je ziet is uit een tekening geknipt. Elke poes is gesplitst in een
 * romp met losse ledematen die om hun gewricht draaien, zodat ze echt bewegen.
 *
 * De layout wordt hier berekend en niet in CSS: elke tekening zegt zelf waar
 * haar banden liggen (`geom`), en het speelveld ertussen rekt mee. Zo klopt het
 * beeld op een smalle telefoon en op een brede iPad.
 */
'use strict';

/* ------------------------------------------------------------------ config */

const ALLOW_WALK = true;

const TILT_DEAD_DEG = 4;        // speling, zodat een scheef gehouden telefoon niet dwaalt
const TILT_FULL_DEG = 22;       // hierboven loopt de poes op volle snelheid
const LEAN_DEG = 7;             // de poes helt over in de looprichting

const ROUND_SECONDS = 60;
const GRAVITY = 2400;           // px/s²
const GRAB_MS = 300;
const GRAB_COOLDOWN_MS = 120;
const ARM_GRAB_DEG = 26;        // armen klappen naar binnen en omhoog
const ARM_JUMP_DEG = 10;
const LEG_SWING_DEG = 17;       // uitslag van de poten tijdens het rennen
const LEG_TUCK_DEG = 24;        // poten optrekken in de klim van een sprong
const LEG_SPREAD_DEG = 14;      // en weer strekken op de weg naar beneden
const WALK_SPEED_PER_W = 0.95;  // schermbreedtes per seconde

// De staart hangt aan een veer: hij volgt de beweging met vertraging en schiet
// er een stukje overheen, in plaats van stijf aan de romp vast te zitten.
const TAIL_STIFF = 85;
const TAIL_DAMP = 8.5;
const TAIL_DRAG_DEG = 26;       // hoever hij achterblijft bij het lopen
const TAIL_LIFT_DEG = 16;       // en bij het op- en neergaan van een sprong
const TAIL_LIMIT_DEG = 55;
// De staart is een ketting: elk segment scharniert aan het vorige en blijft
// achter naarmate dat harder draait. Dat is wat een zweepslag door de staart
// laat lopen in plaats van hem als geheel te laten wijzen.
const TAIL_WHIP = 0.09;         // graden achterstand per graad/s van het vorige
const TAIL_FOLLOW = 0.62;       // hoeveel van de rompbeweging elke schakel meeneemt
const TAIL_SEG_LIMIT = 34;
const TAIL_SEG_SOFTEN = 0.20;   // elk segment naar de punt toe slapper

const SPAWN_MS_START = 950;
const SPAWN_MS_END = 520;
const SCROLL_START = 120;       // px/s
const SCROLL_END = 265;

const RECORD_KEY = 'poezenspel.record';

const TILT_MESSAGE = {
  ok: 'Kantel de telefoon om te lopen.',
  insecure: 'Kantelen werkt alleen via https. Sleep met je duim om te lopen.',
  denied: 'Geen toegang tot de sensor. Sleep met je duim om te lopen.',
  embedded: 'Kantelen kan niet in een ingesloten pagina. Open het spel in een eigen tabblad.',
  silent: 'De sensor geeft niets door. Sleep met je duim om te lopen.',
  unsupported: 'Sleep met je duim om te lopen.',
};
const TILT_PROOF_MS = 1600;

/* ------------------------------------------------------------------ thema's */

// Scharnieren en handen van Hadewychs poes, in de pixels van haar uitsnijcanvas.
// Deze staan apart omdat tools/extract_hw.py ze uitrekent en afdrukt.
const HW = {
  canvas: [1167, 1454],
  armL: [334, 522], armR: [801, 558],
  legL: [452, 994], legR: [749, 982],
  handL: [58, 132], handR: [1094, 133],
  // De staart in vier schakels, elk scharnierend aan het vorige stuk. De
  // scharnieren volgen de krul omhoog; tools/extract_hw.py rekent ze uit.
  tailSegs: [
    { src: 'assets/hw_tail1.png', joint: [831, 935] },
    { src: 'assets/hw_tail2.png', joint: [946, 887] },
    { src: 'assets/hw_tail3.png', joint: [980, 787] },
    { src: 'assets/hw_tail4.png', joint: [983, 682] },
  ],
};

/* Elk thema is één tekening: haar lagen, haar poes met gewrichten, haar
 * knoppen en wat je er verzamelt. `geom` zegt waar de banden liggen — de twee
 * tekeningen delen geen enkele verhouding, dus dat rekent elk thema zelf uit.
 *
 * Scharnieren staan in de pixels van het oorspronkelijke uitsnijcanvas
 * (`canvas`), niet van het verkleinde plaatje, zodat ze meeschalen. */
const THEMES = {
  sigrid: {
    title: ['ROBOT', 'POES'],
    by: 'Sigrid',
    many: 'goudklompjes',
    icon: 'assets/nugget1.png',
    labels: { jump: 'SPRING', grab: 'PAK' },
    layers: {
      field: 'assets/bg_field.jpg',
      ground: 'assets/band_ground.jpg',
      backdrop: 'assets/band_curtain.jpg',
      top: 'assets/band_gold.jpg',
      divider: 'assets/band_rail.jpg',
    },
    fadeBackdrop: true,
    cat: {
      canvas: [1352, 1614],
      size: [0.733, 0.43],
      body: 'assets/kitty_body.png',
      parts: {
        armLeft: { src: 'assets/arm_left.png', pivot: [575, 665] },
        armRight: { src: 'assets/arm_right.png', pivot: [790, 665] },
        legLeft: { src: 'assets/leg_left.png', pivot: [420, 1255] },
        legRight: { src: 'assets/leg_right.png', pivot: [750, 1255] },
      },
      hands: { left: [115, 325], right: [1165, 400] },
      jump: 0.62, grab: 0.36, handR: 0.13, feet: 0.13,
    },
    buttons: {
      left: 'assets/dome_left.png', right: 'assets/dome_right.png',
      leftSize: [0.333, 0.26], rightSize: [0.533, 0.39],
      leftLabel: [0.30, 0.175], rightLabel: [0.34, 0.160],
    },
    pickup: {
      anchor: 'hang',
      srcs: ['assets/nugget1.png', 'assets/nugget2.png', 'assets/nugget3.png'],
      size: [0.169, 0.10],
    },
    geom(W, H) {
      const topH = Math.min(W * 0.138, H * 0.085);
      const divH = Math.min(W * 0.118, H * 0.073);
      const backH = Math.min(W * 0.477, H * 0.28);
      const groundH = Math.min(W * 0.236, H * 0.145);
      const divY = topH - 4;
      const backY = divY + divH - 4;
      const fieldY = backY + backH * 0.31;
      const groundY = H - groundH;
      return {
        topY: 0, topH, divY, divH, backY, backH, groundY, groundH,
        fieldY, fieldH: groundY + groundH * 0.24 - fieldY,
        anchorY: divY + divH - 6,
        // De klompjes hangen aan draden van heel verschillende lengte.
        reach: [backH * 0.25, backH * 1.30], hard: backH * 0.70,
      };
    },
  },

  hadewych: {
    title: ['BLOEMEN', 'POES'],
    by: 'Hadewych',
    many: 'bloemen',
    icon: 'assets/hw_flower1.png',
    labels: { jump: 'SPRING', grab: 'PLUK' },
    layers: {
      // Eén doorlopend streepveld over het hele scherm, met de aarde en de
      // zwarte balk erbovenop. Zo sluiten de strepen boven en onder de balk op
      // elkaar aan -- twee losse panelen deden dat niet.
      field: 'assets/hw_bg_full.jpg',
      ground: null,
      backdrop: null,
      top: 'assets/hw_band_soil.jpg',
      divider: 'assets/hw_band_bar.jpg',
    },
    fadeBackdrop: false,
    cat: {
      canvas: HW.canvas,
      size: [0.86, 0.46],
      body: 'assets/hw_cat_body.png',
      parts: {
        armLeft: { src: 'assets/hw_arm_left.png', pivot: HW.armL },
        armRight: { src: 'assets/hw_arm_right.png', pivot: HW.armR },
        legLeft: { src: 'assets/hw_leg_left.png', pivot: HW.legL },
        legRight: { src: 'assets/hw_leg_right.png', pivot: HW.legR },
      },
      hands: { left: HW.handL, right: HW.handR },
      tail: HW.tailSegs,
      jump: 0.42, grab: 0.40, handR: 0.11, feet: 0.05,
    },
    buttons: {
      left: 'assets/hw_head_left.png', right: 'assets/hw_head_right.png',
      leftSize: [0.38, 0.225], rightSize: [0.38, 0.225],
      leftLabel: [0.31, 0.145], rightLabel: [0.31, 0.145],
    },
    pickup: {
      anchor: 'stand',
      srcs: ['assets/hw_flower1.png', 'assets/hw_flower2.png', 'assets/hw_flower3.png'],
      size: [0.135, 0.078],
      bloomFrac: 0.17,       // waar in het plaatje de bloem zit, van boven af
    },
    geom(W, H) {
      const divH = Math.min(W * 0.135, H * 0.068);
      const divY = Math.min(W * 0.52, H * 0.27);
      const soilH = divH * 0.36;
      const groundH = Math.min(W * 0.17, H * 0.10);
      const anchorY = divY - soilH * 0.45;
      return {
        // Het veld is het hele scherm; aarde en balk liggen erbovenop.
        fieldY: 0, fieldH: H,
        topY: divY - soilH, topH: soilH,
        divY, divH,
        backY: 0, backH: 0,
        groundY: H - groundH, groundH,
        anchorY,
        // Hier is `reach` hoe hoog de bloem boven de aarde uitkomt: een korte
        // steel hangt laag en is makkelijk, een lange staat hoog.
        reach: [anchorY * 0.30, anchorY * 0.92], hard: anchorY * 0.62,
      };
    },
  },
};

/* ------------------------------------------------------------------- state */

const el = (id) => document.getElementById(id);
const dom = {
  stage: el('stage'), layField: el('layField'), layGround: el('layGround'),
  layBackdrop: el('layBackdrop'), layTop: el('layTop'), layDivider: el('layDivider'),
  pickups: el('pickups'), pops: el('pops'), cat: el('cat'),
  score: el('score'), scoreTag: el('scoreTag'), scoreIcon: el('scoreIcon'),
  time: el('time'), timeTag: el('timeTag'),
  btnJump: el('btnJump'), btnGrab: el('btnGrab'), btnSound: el('btnSound'),
  btnJumpImg: el('btnJumpImg'), btnGrabImg: el('btnGrabImg'),
  btnJumpLabel: el('btnJumpLabel'), btnGrabLabel: el('btnGrabLabel'),
  soundIcon: el('soundIcon'), titleSheet: el('titleSheet'), overSheet: el('overSheet'),
  btnAgain: el('btnAgain'), btnSwitch: el('btnSwitch'), finalScore: el('finalScore'),
  finalNoun: el('finalNoun'), recordLine: el('recordLine'), loading: el('loading'),
  tiltHint: el('tiltHint'),
};

let T = null;                   // het thema dat nu speelt
let L = {};                     // afmetingen, opnieuw berekend bij elke resize
let parts = {};                 // naam -> <img> van een ledemaat
let tailSegs = [];              // de staartketting, van romp naar punt
let bodyImg = null;
const kitty = {
  y: 0, vy: 0, airborne: false, grabT: -1, x: 0, targetX: 0,
  lean: 0, drive: 0, legPhase: 0,
};
const tail = { a: [], v: [] };
const keys = { left: false, right: false };
let pickups = [];
let running = false;
let score = 0;
let timeLeft = ROUND_SECONDS;
let elapsed = 0;
let spawnTimer = 0;
let lastFrame = 0;
let pickSeq = 0;

/* ------------------------------------------------------------------- thema */

function applyTheme(theme) {
  T = theme;
  for (const [key, node] of [['field', dom.layField], ['ground', dom.layGround],
                             ['backdrop', dom.layBackdrop], ['top', dom.layTop],
                             ['divider', dom.layDivider]]) {
    const src = T.layers[key];
    node.hidden = !src;
    if (src) node.src = src;
  }
  dom.layBackdrop.classList.toggle('faded', !!T.fadeBackdrop);

  // De ledematen staan vóór de romp in de DOM, zodat de romp ze afdekt waar ze
  // eraan vastzitten en de naad nooit te zien is.
  dom.cat.textContent = '';
  parts = {};
  tailSegs = [];

  // De staart hangt als een ketting in elkaar: segment 2 zit IN segment 1, dus
  // draaiingen stapelen vanzelf en elk stuk scharniert aan het vorige.
  if (T.cat.tail) {
    let host = dom.cat;
    for (const seg of T.cat.tail) {
      const box = document.createElement('div');
      box.className = 'tailSeg';
      const img = new Image();
      img.className = 'catPart';
      img.alt = '';
      img.src = seg.src;
      box.appendChild(img);
      host.appendChild(box);
      tailSegs.push({ box, img, joint: seg.joint });
      host = box;
    }
    tail.a = tailSegs.map(() => 0);
    tail.v = tailSegs.map(() => 0);
  }
  for (const [name, spec] of Object.entries(T.cat.parts)) {
    const img = new Image();
    img.className = 'catPart';
    img.alt = '';
    img.src = spec.src;
    dom.cat.appendChild(img);
    parts[name] = img;
  }
  bodyImg = new Image();
  bodyImg.className = 'catPart';
  bodyImg.alt = '';
  bodyImg.src = T.cat.body;
  dom.cat.appendChild(bodyImg);

  dom.btnJumpImg.src = T.buttons.left;
  dom.btnGrabImg.src = T.buttons.right;
  dom.btnJumpLabel.textContent = T.labels.jump;
  dom.btnGrabLabel.textContent = T.labels.grab;
  dom.btnJump.setAttribute('aria-label', T.labels.jump);
  dom.btnGrab.setAttribute('aria-label', T.labels.grab);
  dom.scoreIcon.src = T.icon;
  dom.finalNoun.textContent = T.many;

  for (const p of pickups) p.node.remove();
  pickups = [];
}

/* ------------------------------------------------------------------ layout */

function ratio(img) {
  return img && img.naturalWidth ? img.naturalWidth / img.naturalHeight : 1;
}

function layout() {
  if (!T) return;
  const W = dom.stage.clientWidth;
  const H = dom.stage.clientHeight;
  const g = T.geom(W, H);

  const catW = Math.min(W * T.cat.size[0], H * T.cat.size[1]);
  const catH = catW / (T.cat.canvas[0] / T.cat.canvas[1]);
  const pickW = Math.min(W * T.pickup.size[0], H * T.pickup.size[1]);

  L = {
    W, H, ...g, catW, catH, pickW,
    feetY: g.groundY + g.groundH * T.cat.feet,
    jumpH: catH * T.cat.jump,
    grabReach: catH * T.cat.grab,
    handR: catW * T.cat.handR,
    walkSpeed: W * WALK_SPEED_PER_W,
  };
  L.jumpV = Math.sqrt(2 * GRAVITY * L.jumpH);
  L.catRestX = (W - catW) / 2;
  // Bij draaien of een venster dat van maat verandert moet de poes mee naar het
  // nieuwe midden; anders blijft hij op de oude x staan en loopt hij uit beeld.
  if (!ALLOW_WALK || !kitty.x) {
    kitty.x = L.catRestX;
    kitty.targetX = L.catRestX;
  } else {
    kitty.x = Math.max(0, Math.min(W - catW, kitty.x));
    kitty.targetX = Math.max(0, Math.min(W - catW, kitty.targetX));
  }

  place(dom.layField, 0, g.fieldY, W, g.fieldH);
  place(dom.layGround, 0, g.groundY, W, g.groundH);
  if (T.layers.backdrop) place(dom.layBackdrop, 0, g.backY, W, g.backH);
  place(dom.layTop, 0, g.topY, W, g.topH);
  place(dom.layDivider, 0, g.divY, W, g.divH);

  // De poes-div krijgt een echte maat, niet alleen een transform: hij is het
  // blok waar de losse delen hun percentages tegen afrekenen.
  dom.cat.style.width = `${catW}px`;
  dom.cat.style.height = `${catH}px`;
  const [cw, chh] = T.cat.canvas;
  for (const seg of tailSegs) {
    place(seg.box, 0, 0, catW, catH);
    place(seg.img, 0, 0, catW, catH);
    seg.box.style.transformOrigin =
      `${seg.joint[0] / cw * catW}px ${seg.joint[1] / chh * catH}px`;
  }
  for (const [name, img] of Object.entries(parts)) {
    place(img, 0, 0, catW, catH);
    const [px, py] = T.cat.parts[name].pivot;
    img.style.transformOrigin = `${px / cw * catW}px ${py / chh * catH}px`;
  }
  place(bodyImg, 0, 0, catW, catH);

  const b = T.buttons;
  const lw = Math.min(W * b.leftSize[0], H * b.leftSize[1]);
  const rw = Math.min(W * b.rightSize[0], H * b.rightSize[1]);
  const lh = lw / ratio(dom.btnJumpImg);
  const rh = rw / ratio(dom.btnGrabImg);
  place(dom.btnJump, -lw * 0.06, H - lh, lw, lh);
  place(dom.btnGrab, W - rw * 0.94, H - rh, rw, rh);
  label(dom.btnJumpLabel, lw, lh, b.leftLabel);
  label(dom.btnGrabLabel, rw, rh, b.rightLabel);

  for (const p of pickups) sizePickup(p);
  render();
}

function place(node, x, y, w, h) {
  node.style.left = `${x}px`;
  node.style.top = `${y}px`;
  node.style.width = `${w}px`;
  node.style.height = `${h}px`;
}

function label(span, w, h, [topFrac, sizeFrac]) {
  span.style.top = `${h * topFrac}px`;
  span.style.fontSize = `${Math.round(w * sizeFrac)}px`;
}

/* ----------------------------------------------------------------- oogsten */

function spawnPickup() {
  const kind = pickSeq++ % T.pickup.srcs.length;
  const reach = L.reach[0] + Math.random() * (L.reach[1] - L.reach[0]);
  const node = document.createElement('div');
  node.className = `pickup ${T.pickup.anchor}`;
  const img = new Image();
  img.alt = '';
  img.src = T.pickup.srcs[kind];
  let wireEl = null;
  if (T.pickup.anchor === 'hang') {
    wireEl = document.createElement('div');
    wireEl.className = 'wire';
    node.appendChild(wireEl);
  }
  node.appendChild(img);
  dom.pickups.appendChild(node);

  const p = {
    kind, reach, node, img, wireEl,
    x: L.W + L.pickW,
    phase: Math.random() * Math.PI * 2,
    dead: false,
    points: reach > L.hard ? 2 : 1,
  };
  sizePickup(p);
  pickups.push(p);
}

function sizePickup(p) {
  const w = L.pickW;
  p.w = w;
  p.img.style.width = `${w}px`;
  p.node.style.width = `${w}px`;
  if (T.pickup.anchor === 'hang') {
    // Aan een draad onder de rail: eerst de draad, dan het klompje.
    const h = w / ratio(p.img);
    p.h = h;
    p.img.style.height = `${h}px`;
    p.img.style.top = `${p.reach}px`;
    p.node.style.height = `${p.reach + h}px`;
    p.wireEl.style.height = `${p.reach}px`;
    p.top = L.anchorY;
    p.catchY = L.anchorY + p.reach + h / 2;
  } else {
    // Uit de aarde omhoog: de steel staat in de grond en de bloem komt erboven
    // uit, dus `reach` IS de hoogte van het plaatje.
    const h = p.reach;
    p.h = h;
    p.img.style.width = `${h * ratio(p.img)}px`;
    p.img.style.height = `${h}px`;
    p.img.style.top = '0px';
    p.w = h * ratio(p.img);
    p.node.style.width = `${p.w}px`;
    p.node.style.height = `${h}px`;
    p.top = L.anchorY - h;
    p.catchY = p.top + h * T.pickup.bloomFrac;
  }
}

function swingOf(p) {
  return Math.sin(elapsed * 1.6 + p.phase) * (T.pickup.anchor === 'hang' ? 0.10 : 0.055);
}

function pickupCentre(p, swing) {
  const cx = p.x + p.w / 2;
  if (T.pickup.anchor === 'hang') {
    const d = p.reach + p.h / 2;
    return {
      x: cx + Math.sin(swing) * d,
      y: L.anchorY + Math.cos(swing) * d,
      r: Math.min(p.w, p.h) * 0.42,
    };
  }
  const d = L.anchorY - p.catchY;
  return {
    x: cx - Math.sin(swing) * d,
    y: L.anchorY - Math.cos(swing) * d,
    r: p.w * 0.40,
  };
}

/* --------------------------------------------------------------------- poes */

function armAngles() {
  const grab = grabProgress();
  const lift = kitty.airborne ? Math.min(1, Math.abs(kitty.vy) / L.jumpV) : 0;
  const idle = running ? Math.sin(elapsed * 2.1) * 3 : Math.sin(elapsed * 1.3) * 2.2;
  const swing = grab * ARM_GRAB_DEG + lift * ARM_JUMP_DEG + idle;
  return { left: swing, right: -swing };
}

function legAngles() {
  if (kitty.airborne) {
    const t = Math.min(1, Math.abs(kitty.vy) / L.jumpV);
    const a = kitty.vy > 0 ? -LEG_TUCK_DEG * t : LEG_SPREAD_DEG * t;
    return { left: a, right: a * 0.7 };
  }
  const amp = LEG_SWING_DEG * Math.abs(kitty.drive);
  if (amp < 0.5) {
    const idle = Math.sin(elapsed * 2.1) * 1.2;
    return { left: idle, right: -idle };
  }
  const s = Math.sin(kitty.legPhase);
  return { left: s * amp, right: -s * amp };
}

// De staart wordt niet gezet maar geintegreerd: elk segment hangt aan een veer
// met demping. Het eerste volgt de romp, elk volgend segment blijft achter bij
// hoe hard zijn voorganger draait. Daardoor loopt er een zweep door de staart
// bij het keren en zwiept hij na een sprong uit, in plaats van stijf mee te
// draaien met het lijf.
function stepTail(dt) {
  if (!tailSegs.length) return;
  const base = -kitty.drive * TAIL_DRAG_DEG
    - (kitty.vy / L.jumpV) * TAIL_LIFT_DEG
    + Math.sin(elapsed * 1.7) * 3;
  for (let i = 0; i < tailSegs.length; i++) {
    // Elke schakel neemt een steeds kleiner deel van de rompbeweging mee, zodat
    // de staart over zijn hele lengte krult en niet alleen bij de aanzet -- de
    // naijling alleen doven uit na twee schakels en dan beweegt de punt niet.
    const target = i === 0
      ? base
      : base * Math.pow(TAIL_FOLLOW, i) - tail.v[i - 1] * TAIL_WHIP;
    const soft = 1 - i * TAIL_SEG_SOFTEN;      // naar de punt toe slapper
    const accel = -TAIL_STIFF * soft * (tail.a[i] - target)
      - TAIL_DAMP * tail.v[i];
    tail.v[i] += accel * dt;
    tail.a[i] += tail.v[i] * dt;
    const lim = i === 0 ? TAIL_LIMIT_DEG : TAIL_SEG_LIMIT;
    if (tail.a[i] > lim) { tail.a[i] = lim; tail.v[i] = 0; }
    if (tail.a[i] < -lim) { tail.a[i] = -lim; tail.v[i] = 0; }
  }
}

// 0 in rust, 1 op het hoogste punt van de greep.
function grabProgress() {
  if (kitty.grabT < 0) return 0;
  return Math.sin(Math.PI * Math.min(1, kitty.grabT / GRAB_MS));
}

function handPositions() {
  const a = armAngles();
  const top = L.feetY - L.catH - kitty.y - grabProgress() * L.grabReach;
  const [cw, chh] = T.cat.canvas;
  const out = {};
  for (const side of ['left', 'right']) {
    const spec = T.cat.parts[side === 'left' ? 'armLeft' : 'armRight'];
    const px = spec.pivot[0] / cw * L.catW;
    const py = spec.pivot[1] / chh * L.catH;
    const rx = T.cat.hands[side][0] / cw * L.catW - px;
    const ry = T.cat.hands[side][1] / chh * L.catH - py;
    const t = a[side] * Math.PI / 180;
    const cos = Math.cos(t), sin = Math.sin(t);
    out[side] = {
      x: kitty.x + px + rx * cos - ry * sin,
      y: top + py + rx * sin + ry * cos,
    };
  }
  return out;
}

function jump() {
  if (!running || kitty.airborne) return;
  kitty.airborne = true;
  kitty.vy = L.jumpV;
  sound.jump();
}

function grab() {
  if (!running || kitty.grabT >= 0) return;
  kitty.grabT = 0;
  sound.grab();
}

/* -------------------------------------------------------------------- loop */

function update(dt) {
  elapsed += dt;
  if (!T) return;
  stepTail(dt);
  if (!running) return;

  timeLeft -= dt;
  if (timeLeft <= 0) { timeLeft = 0; endRound(); }
  showTime();

  if (kitty.airborne) {
    kitty.vy -= GRAVITY * dt;
    kitty.y += kitty.vy * dt;
    if (kitty.y <= 0) { kitty.y = 0; kitty.vy = 0; kitty.airborne = false; }
  }
  if (kitty.grabT >= 0) {
    kitty.grabT += dt * 1000;
    if (kitty.grabT > GRAB_MS + GRAB_COOLDOWN_MS) kitty.grabT = -1;
  }
  if (ALLOW_WALK) {
    const drive = walkInput();
    kitty.drive = drive;
    // Hoe harder hij loopt, hoe sneller de pas.
    if (drive !== 0 && !kitty.airborne) kitty.legPhase += dt * (5 + 9 * Math.abs(drive));
    if (drive !== 0) {
      kitty.x += drive * L.walkSpeed * dt;
      kitty.targetX = kitty.x;
    } else if (kitty.targetX !== kitty.x) {
      // Slepen mikt op een punt; kantelen stuurt rechtstreeks.
      const dx = kitty.targetX - kitty.x;
      const step = L.walkSpeed * dt;
      kitty.x += Math.abs(dx) <= step ? dx : Math.sign(dx) * step;
    }
    kitty.x = Math.max(0, Math.min(L.W - L.catW, kitty.x));
    kitty.lean += (drive * LEAN_DEG - kitty.lean) * Math.min(1, dt * 9);
  }

  const t = Math.min(1, elapsed / ROUND_SECONDS);
  const speed = SCROLL_START + (SCROLL_END - SCROLL_START) * t;
  for (const p of pickups) p.x -= speed * dt;

  spawnTimer -= dt * 1000;
  if (spawnTimer <= 0) {
    spawnPickup();
    spawnTimer = SPAWN_MS_START + (SPAWN_MS_END - SPAWN_MS_START) * t;
  }

  // Pakken telt alleen terwijl de klauwen dichtgaan: springen alleen levert
  // niets op, en dat is precies wat de twee knoppen uit elkaar houdt.
  if (kitty.grabT >= 0 && kitty.grabT <= GRAB_MS) {
    const hands = handPositions();
    for (const p of pickups) {
      if (p.dead) continue;
      const c = pickupCentre(p, swingOf(p));
      for (const side of ['left', 'right']) {
        const h = hands[side];
        if (Math.hypot(h.x - c.x, h.y - c.y) < L.handR + c.r) { catchPickup(p, c); break; }
      }
    }
  }

  for (const p of pickups) {
    if (p.dead || p.x >= -p.w * 2) continue;
    p.node.remove();
    p.dead = true;
  }
  pickups = pickups.filter((p) => !p.dead);
}

function catchPickup(p, centre) {
  p.dead = true;
  p.node.remove();
  score += p.points;
  dom.score.textContent = String(score);
  dom.scoreTag.classList.remove('bump');
  void dom.scoreTag.offsetWidth;          // herstart de animatie
  dom.scoreTag.classList.add('bump');
  popup(`+${p.points}`, centre.x, centre.y);
  sound.catch_();
}

function popup(text, x, y) {
  const p = document.createElement('div');
  p.className = 'pop';
  p.textContent = text;
  p.style.fontSize = `${Math.round(L.pickW * 0.62)}px`;
  p.style.left = `${x}px`;
  p.style.top = `${y}px`;
  dom.pops.appendChild(p);
  setTimeout(() => p.remove(), 750);
}

function render() {
  if (!T) return;
  const bob = running && !kitty.airborne ? Math.sin(elapsed * 2.1) * 2 : 0;
  const top = L.feetY - L.catH - kitty.y - grabProgress() * L.grabReach + bob;
  dom.cat.style.transform =
    `translate3d(${kitty.x}px, ${top}px, 0) rotate(${kitty.lean.toFixed(2)}deg)`;

  const a = armAngles();
  const lg = legAngles();
  const angle = {
    armLeft: a.left, armRight: a.right,
    legLeft: lg.left, legRight: lg.right,
  };
  for (const [name, img] of Object.entries(parts)) {
    img.style.transform = `rotate(${(angle[name] || 0).toFixed(2)}deg)`;
  }
  for (let i = 0; i < tailSegs.length; i++) {
    tailSegs[i].box.style.transform = `rotate(${tail.a[i].toFixed(2)}deg)`;
  }

  for (const p of pickups) {
    const deg = swingOf(p) * 180 / Math.PI;
    p.node.style.transform = `translate3d(${p.x}px, ${p.top}px, 0) rotate(${deg}deg)`;
  }
}

function frame(now) {
  const dt = Math.min(0.05, lastFrame ? (now - lastFrame) / 1000 : 0);
  lastFrame = now;
  update(dt);
  render();
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------- ronde */

function startRound() {
  score = 0;
  timeLeft = ROUND_SECONDS;
  elapsed = 0;
  spawnTimer = 0;
  kitty.y = 0; kitty.vy = 0; kitty.airborne = false; kitty.grabT = -1;
  kitty.x = L.catRestX; kitty.targetX = L.catRestX;
  kitty.lean = 0; kitty.drive = 0; kitty.legPhase = 0;
  tail.a = tail.a.map(() => 0); tail.v = tail.v.map(() => 0);
  for (const p of pickups) p.node.remove();
  pickups = [];
  dom.score.textContent = '0';
  dom.timeTag.classList.remove('low');
  showTime();
  dom.titleSheet.classList.add('hidden');
  dom.overSheet.classList.add('hidden');
  running = true;
}

function endRound() {
  running = false;
  dom.finalScore.textContent = String(score);
  dom.finalNoun.textContent = T.many;
  dom.recordLine.textContent = `record · ${saveRecord(score)}`;
  dom.overSheet.classList.remove('hidden');
  sound.end();
}

function showTime() {
  const s = Math.max(0, Math.ceil(timeLeft));
  dom.time.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  dom.timeTag.classList.toggle('low', s <= 10);
}

// Elke tekening houdt haar eigen record bij; het zijn twee verschillende spellen.
function saveRecord(value) {
  const key = `${RECORD_KEY}.${T.by}`;
  try {
    const best = Math.max(value, parseInt(localStorage.getItem(key) || '0', 10) || 0);
    localStorage.setItem(key, String(best));
    return best;
  } catch (_) {
    return value;      // privemodus of geblokkeerde opslag; het spel gaat door
  }
}

/* ------------------------------------------------------------------ kantel */

const tilt = (() => {
  let active = false;
  let raw = 0;
  let neutral = 0;
  let asked = false;
  let reason = 'unsupported';
  let reading = false;
  let onChange = null;

  // Welke as links-rechts is, hangt van de stand van het scherm af: rechtop is
  // dat gamma, gedraaid is het beta, en op z'n kop draaien de tekens om.
  function sideways(e) {
    const angle = (screen.orientation && screen.orientation.angle)
      || window.orientation || 0;
    const g = e.gamma || 0;
    const b = e.beta || 0;
    if (angle === 90) return -b;
    if (angle === 270 || angle === -90) return b;
    if (angle === 180) return -g;
    return g;
  }

  function onOrient(e) {
    reading = true;
    raw = sideways(e);
  }

  // iOS geeft de bewegingssensor pas na een expliciete vraag, en die vraag mag
  // alleen uit een echte aanraking komen — vandaar de knop waarmee je kiest.
  async function request() {
    if (active) return 'ok';
    if (asked) return reason;
    asked = true;
    const DOE = window.DeviceOrientationEvent;
    if (!DOE) { reason = 'unsupported'; return reason; }
    // Safari geeft de sensor alleen op een beveiligde herkomst. Over gewone
    // http blijft de vraag onbeantwoord, en dat is niet te zien aan de fout.
    if (!window.isSecureContext) { reason = 'insecure'; return reason; }
    try {
      if (typeof DOE.requestPermission === 'function') {
        if (await DOE.requestPermission() !== 'granted') {
          reason = 'denied';
          return reason;
        }
      }
      window.addEventListener('deviceorientation', onOrient);
      active = true;
      reason = 'ok';
      // Toestemming krijgen is niet hetzelfde als metingen krijgen. Een pagina
      // in een iframe krijgt de sensor alleen als de insluiter hem doorgeeft
      // via allow="gyroscope; accelerometer"; doet die dat niet, dan zegt de
      // vraag gewoon ja en komt er daarna nooit iets binnen. Dus: afwachten.
      setTimeout(() => {
        if (reading) return;
        active = false;
        reason = window.self !== window.top ? 'embedded' : 'silent';
        if (onChange) onChange(reason);
      }, TILT_PROOF_MS);
    } catch (_) {
      reason = 'denied';   // geweigerd of geblokkeerd: slepen blijft over
    }
    return reason;
  }

  return {
    request,
    set onchange(fn) { onChange = fn; },
    get active() { return active; },
    get reason() { return reason; },
    // De stand waarin het toestel bij de start ligt telt als recht vooruit,
    // zodat onderuitgezakt spelen net zo goed werkt als rechtop.
    calibrate() { neutral = raw; },
    amount() {
      if (!active) return 0;
      const d = raw - neutral;
      const past = Math.abs(d) - TILT_DEAD_DEG;
      if (past <= 0) return 0;
      return Math.sign(d) * Math.min(1, past / (TILT_FULL_DEG - TILT_DEAD_DEG));
    },
  };
})();

// Kantelen stuurt; pijltjestoetsen doen het op een laptop. Slepen blijft over
// voor een toestel dat geen sensor geeft of waar die geweigerd is.
function walkInput() {
  const t = tilt.amount();
  if (t !== 0) return t;
  if (keys.left && !keys.right) return -1;
  if (keys.right && !keys.left) return 1;
  return 0;
}

/* ------------------------------------------------------------------ geluid */

const sound = (() => {
  let ctx = null;
  let on = true;

  function ensure() {
    // iOS geeft pas audio na een echte aanraking, dus de context wordt bij de
    // eerste tik gemaakt en niet bij het laden.
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function tone(freq, start, dur, peak, type) {
    const c = ensure();
    if (!c || !on) return;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = type || 'triangle';
    osc.frequency.setValueAtTime(freq, c.currentTime + start);
    gain.gain.setValueAtTime(0.0001, c.currentTime + start);
    gain.gain.exponentialRampToValueAtTime(peak, c.currentTime + start + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + start + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(c.currentTime + start);
    osc.stop(c.currentTime + start + dur + 0.02);
  }

  return {
    unlock: ensure,
    jump: () => tone(300, 0, 0.11, 0.10, 'square'),
    grab: () => tone(170, 0, 0.07, 0.07, 'square'),
    catch_: () => { tone(880, 0, 0.10, 0.13); tone(1320, 0.07, 0.16, 0.11); },
    end: () => { tone(660, 0, 0.16, 0.12); tone(520, 0.14, 0.18, 0.12); tone(390, 0.3, 0.32, 0.12); },
    toggle: () => {
      on = !on;
      if (on) ensure();
      dom.btnSound.classList.toggle('off', !on);
      dom.soundIcon.textContent = on ? '♪' : '✕';
      return on;
    },
  };
})();

/* ------------------------------------------------------------------- input */

function hold(btn, action) {
  const down = (e) => {
    e.preventDefault();
    sound.unlock();
    btn.classList.add('pressed');
    action();
  };
  const up = () => btn.classList.remove('pressed');
  btn.addEventListener('pointerdown', down);
  btn.addEventListener('pointerup', up);
  btn.addEventListener('pointercancel', up);
  btn.addEventListener('pointerleave', up);
}

hold(dom.btnJump, jump);
hold(dom.btnGrab, grab);

dom.btnSound.addEventListener('click', () => sound.toggle());

function showTiltReason(why) {
  dom.tiltHint.textContent = TILT_MESSAGE[why] || TILT_MESSAGE.unsupported;
  dom.tiltHint.hidden = false;
}

async function begin(theme) {
  sound.unlock();
  if (theme && theme !== T) {
    applyTheme(theme);
    layout();
  }
  if (ALLOW_WALK) {
    // Wachten tot de sensorvraag beantwoord is: de ronde mag niet achter een
    // systeemdialoog beginnen weglopen.
    const why = await tilt.request();
    tilt.calibrate();
    showTiltReason(why);
  }
  startRound();
}

for (const btn of document.querySelectorAll('.pick')) {
  btn.addEventListener('click', () => begin(THEMES[btn.dataset.theme]));
}
dom.btnAgain.addEventListener('click', () => begin(null));
dom.btnSwitch.addEventListener('click', () => {
  dom.overSheet.classList.add('hidden');
  dom.titleSheet.classList.remove('hidden');
});

window.addEventListener('keydown', (e) => {
  if (e.code === 'ArrowLeft') keys.left = true;
  if (e.code === 'ArrowRight') keys.right = true;
  if (e.repeat) return;
  if (e.code === 'Space') { e.preventDefault(); jump(); }
  if (e.code === 'Enter' || e.code === 'KeyG') { e.preventDefault(); grab(); }
});

window.addEventListener('keyup', (e) => {
  if (e.code === 'ArrowLeft') keys.left = false;
  if (e.code === 'ArrowRight') keys.right = false;
});

if (ALLOW_WALK) {
  const track = (e) => {
    if (tilt.active || e.target.closest('button')) return;
    kitty.targetX = Math.max(0, Math.min(L.W - L.catW, e.clientX - L.catW / 2));
  };
  dom.stage.addEventListener('pointerdown', track);
  dom.stage.addEventListener('pointermove', (e) => { if (e.buttons) track(e); });
}

// De uitkomst kan later alsnog omslaan, als blijkt dat er geen metingen komen.
tilt.onchange = showTiltReason;

// Een tab die terugkomt na lang weg te zijn geweest mag niet in één klap een
// halve ronde aan tijd inhalen.
document.addEventListener('visibilitychange', () => { lastFrame = 0; });
window.addEventListener('resize', layout);
window.addEventListener('orientationchange', () => setTimeout(layout, 120));
if (window.visualViewport) window.visualViewport.addEventListener('resize', layout);

/* -------------------------------------------------------------------- boot */

function whenLoaded(done) {
  const imgs = Array.from(document.images).filter((i) => i.getAttribute('src'));
  let pending = imgs.filter((i) => !i.complete).length;
  if (pending === 0) { done(); return; }
  // Ook bij een kapot plaatje doorgaan: een spel dat blijft hangen op "Laden"
  // is erger dan een spel met een gat erin.
  const tick = () => { if (--pending <= 0) done(); };
  for (const img of imgs) {
    if (img.complete) continue;
    img.addEventListener('load', tick, { once: true });
    img.addEventListener('error', tick, { once: true });
  }
  setTimeout(() => { if (pending > 0) { pending = 0; done(); } }, 6000);
}

// Eén tekening staat alvast klaar achter het keuzescherm, zodat er iets te zien
// is terwijl je kiest; kiezen wisselt hem desnoods om.
applyTheme(THEMES.sigrid);
whenLoaded(() => {
  layout();
  dom.loading.classList.add('done');
  requestAnimationFrame(frame);
});
