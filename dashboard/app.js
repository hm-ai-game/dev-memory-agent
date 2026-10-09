const canvas = document.querySelector("#space");
const ctx = canvas.getContext("2d", { alpha: false });
const panel = document.querySelector("#panel");
const panelBody = document.querySelector("#panel-body");
const card = document.querySelector("#node-card");
const toolbar = document.querySelector("#toolbar");
const galaxyLabels = document.querySelector("#galaxy-labels");
const coverNav = document.querySelector("#cover-nav");
const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");

const state = {
  projects: [], currentId: null, current: null, scene: "universe", panel: null,
  selected: null, hovered: null, camera: { x: 0, y: 0, scale: 1 },
  driftPhase: 0, lastInteraction: performance.now(), lastFrame: 0,
  pointer: null, stars: [], width: 0, height: 0, galaxies: new Map(), universeImage: null,
  maskedUniverse: null,
};

const kindNames = {
  requirement: "需求", milestone: "里程碑", decision: "决策",
  implementation: "实现", verification: "验证", failed_approach: "失败路径",
  blocker: "阻碍", direction_change: "方向变更",
};
const statusNames = {
  planned: "待开发", in_progress: "进行中", completed: "已完成",
  failed: "失败", blocked: "受阻", superseded: "已替代",
  pending_approval: "待确认",
};
const evidenceNames = { unverified: "未验证", reported: "已报告", observed: "已观察", tested: "已测试" };

function el(tag, className = "", value = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== "") node.textContent = String(value);
  return node;
}

function hash(value) {
  let result = 2166136261;
  for (const char of String(value)) {
    result ^= char.charCodeAt(0);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}

function random(seed) {
  let value = seed >>> 0;
  return () => {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function halton(index, base) {
  let result = 0, fraction = 1 / base, n = index;
  while (n > 0) {
    result += fraction * (n % base);
    n = Math.floor(n / base);
    fraction /= base;
  }
  return result;
}

function clamp(value, low, high) { return Math.min(high, Math.max(low, value)); }
function touch() { state.lastInteraction = performance.now(); }

function toast(message) {
  const item = document.querySelector("#toast");
  item.textContent = message;
  item.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => item.classList.add("hidden"), 3600);
}

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "读取失败");
  return data;
}

async function loadProjects() {
  const data = await api("/api/state");
  state.projects = data.projects;
  if (state.currentId && !state.projects.some(project => project.id === state.currentId)) {
    state.currentId = null;
    state.current = null;
    state.scene = "universe";
    state.selected = null;
  }
  if (!state.currentId && state.projects.length) state.currentId = state.projects.find(project => !project.error)?.id || null;
  renderGalaxyLabels();
  updateLabels();
}

async function loadCurrent() {
  if (!state.currentId) return false;
  state.current = await api(`/api/projects/${encodeURIComponent(state.currentId)}`);
  updateLabels();
  return true;
}

async function chooseProject(id) {
  state.currentId = id;
  await loadCurrent();
  state.scene = "project";
  state.selected = null;
  state.panel = null;
  resetView();
  updateLabels();
  updateToolbar();
  renderPanel();
  renderCard();
}

function updateLabels() {
  const total = state.projects.reduce((sum, project) => sum + (project.node_count || 0), 0);
  document.querySelector("#app").classList.toggle("is-universe", state.scene === "universe");
  document.querySelector("#app").classList.toggle("is-project", state.scene === "project");
  if (state.scene === "universe") {
    document.querySelector("#scene-title").textContent = "Universe";
    document.querySelector("#scene-subtitle").textContent = "每片星云是一段项目旅程，每颗亮星是一条开发记忆。";
    document.querySelector("#project-count").textContent = state.projects.length;
    document.querySelector("#project-count").nextElementSibling.textContent = "项目星云";
    document.querySelector("#node-count").textContent = total;
    document.querySelector("#node-count").nextElementSibling.textContent = "记忆节点";
    document.querySelector("#scene-hint").textContent = "点击项目名称进入 · 滚轮缩放 · 拖动浏览";
  } else {
    const project = state.current?.project || state.projects.find(item => item.id === state.currentId);
    document.querySelector("#scene-title").textContent = project?.name || "项目星云";
    document.querySelector("#scene-subtitle").textContent = project?.goal || "每颗亮星对应一条开发记忆。";
    document.querySelector("#project-count").textContent = project?.node_count || 0;
    document.querySelector("#project-count").nextElementSibling.textContent = "记忆节点";
    document.querySelector("#node-count").textContent = project?.completed || 0;
    document.querySelector("#node-count").nextElementSibling.textContent = "已完成";
    document.querySelector("#scene-hint").textContent = "点击亮星查看节点 · 滚轮缩放 · 拖动浏览";
  }
}

function updateToolbar() {
  for (const button of toolbar.querySelectorAll(".tool")) {
    const action = button.dataset.action;
    button.classList.toggle("active", action === (state.panel || state.scene));
  }
  for (const button of coverNav.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.action === (state.panel || state.scene));
  }
}

function resize() {
  state.width = canvas.clientWidth;
  state.height = canvas.clientHeight;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(state.width * ratio);
  canvas.height = Math.round(state.height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const rand = random(936182);
  state.stars = Array.from({ length: Math.round(clamp(state.width * state.height / 1450, 160, 1250)) }, () => ({
    x: rand(), y: rand(), radius: rand() < .025 ? 1.1 : .2 + rand() * .4,
    alpha: .07 + rand() * .3,
  }));
  renderGalaxyLabels();
}

function drift() {
  return { x: Math.sin(state.driftPhase) * 10, y: Math.cos(state.driftPhase * .8) * 6 };
}

function screenPoint(x, y) {
  const { width, height, camera } = state;
  const offset = drift();
  return {
    x: (x - width / 2) * camera.scale + width / 2 + camera.x + offset.x,
    y: (y - height / 2) * camera.scale + height / 2 + camera.y + offset.y,
  };
}

function worldPoint(x, y) {
  const { width, height, camera } = state;
  const offset = drift();
  return {
    x: (x - width / 2 - camera.x - offset.x) / camera.scale + width / 2,
    y: (y - height / 2 - camera.y - offset.y) / camera.scale + height / 2,
  };
}

const referenceSlots = [
  { x: .178, y: .298, width: .125 },
  { x: .724, y: .188, width: .125 },
  { x: .87, y: .635, width: .125 },
  { x: .078, y: .634, width: .125 },
];
const extraLabelAnchors = [
  { x: .27, y: .49, width: .17, height: .23 },
  { x: .74, y: .27, width: .17, height: .2 },
  { x: .72, y: .72, width: .17, height: .2 },
  { x: .1, y: .72, width: .17, height: .2 },
];

function universeBounds() {
  const image = state.universeImage;
  const imageWidth = image?.naturalWidth || 1680;
  const imageHeight = image?.naturalHeight || 941;
  const fit = Math.min(state.width / imageWidth, state.height / imageHeight);
  const width = imageWidth * fit * state.camera.scale;
  const height = imageHeight * fit * state.camera.scale;
  const offset = drift();
  const limitX = Math.max(0, (width - state.width) / 2 - 24);
  const limitY = Math.max(0, (height - state.height) / 2 - 24);
  state.camera.x = clamp(state.camera.x + offset.x, -limitX, limitX) - offset.x;
  state.camera.y = clamp(state.camera.y + offset.y, -limitY, limitY) - offset.y;
  return { x: (state.width - width) / 2 + state.camera.x + offset.x,
    y: (state.height - height) / 2 + state.camera.y + offset.y, width, height };
}

function renderGalaxyLabels() {
  galaxyLabels.replaceChildren();
  referenceSlots.forEach((slot, index) => {
    const button = el("button", "galaxy-label reference-slot");
    button.type = "button";
    const project = state.projects[index];
    button.append(el("span", "", project?.name || "等待项目"),
      el("small", "", project ? `${project.node_count || 0} 条记忆` : "尚未连接"));
    button.disabled = !project || Boolean(project.error);
    if (!button.disabled) {
      button.setAttribute("aria-label", `进入项目 ${project.name}`);
      button.dataset.projectName = project.name;
      button.title = `进入 ${project.name}`;
      button.addEventListener("click", () => chooseProject(project.id).catch(error => toast(error.message)));
    } else {
      button.setAttribute("aria-label", "等待项目连接");
    }
    galaxyLabels.append(button);
  });
  if (state.projects.length > referenceSlots.length) {
    const extraProjects = state.projects.slice(referenceSlots.length);
    extraLabelAnchors.forEach((anchor, cluster) => {
      const stack = el("div", "galaxy-tag-stack");
      stack.dataset.cluster = String(cluster);
      extraProjects.forEach((project, index) => {
        if (index % extraLabelAnchors.length !== cluster) return;
        const button = el("button", "galaxy-label extra-galaxy-label");
        button.type = "button";
        button.append(el("span", "", project.name),
          el("small", "", `${project.node_count || 0} 条记忆`));
        button.disabled = Boolean(project.error);
        button.setAttribute("aria-label", button.disabled ? `${project.name} 暂不可进入` : `进入项目 ${project.name}`);
        button.title = button.disabled ? project.error : `进入 ${project.name}`;
        if (!button.disabled) button.addEventListener("click", () => chooseProject(project.id).catch(error => toast(error.message)));
        stack.append(button);
      });
      if (stack.childElementCount) galaxyLabels.append(stack);
    });
  }
  positionGalaxyLabels();
}

function positionGalaxyLabels() {
  if (state.scene !== "universe") return;
  const bounds = universeBounds();
  referenceSlots.forEach((slot, index) => {
    const button = galaxyLabels.children[index];
    if (!button) return;
    button.style.left = `${bounds.x + slot.x * bounds.width}px`;
    button.style.top = `${bounds.y + slot.y * bounds.height}px`;
    button.style.width = `${slot.width * bounds.width}px`;
    button.style.height = `${Math.max(40, .051 * bounds.height)}px`;
    button.style.fontSize = `${clamp(bounds.width / 92, 11, 18)}px`;
    button.style.paddingLeft = `${clamp(bounds.width / 105, 10, 18)}px`;
  });
  for (const stack of galaxyLabels.querySelectorAll(".galaxy-tag-stack")) {
    const anchor = extraLabelAnchors[Number(stack.dataset.cluster)];
    stack.style.left = `${bounds.x + anchor.x * bounds.width}px`;
    stack.style.top = `${bounds.y + anchor.y * bounds.height}px`;
    stack.style.width = `${anchor.width * bounds.width}px`;
    stack.style.maxHeight = `${anchor.height * bounds.height}px`;
    stack.style.fontSize = `${clamp(bounds.width / 92, 11, 18)}px`;
  }
  coverNav.style.left = `${bounds.x + bounds.width * .014}px`;
  coverNav.style.top = `${bounds.y + bounds.height * .019}px`;
  coverNav.style.width = `${bounds.width * .325}px`;
  coverNav.style.height = `${bounds.height * .07}px`;
  coverNav.style.fontSize = `${clamp(bounds.width / 100, 10, 16)}px`;
}

function projectNodes() {
  const nodes = state.current?.nodes || [];
  const W = state.width, H = state.height;
  return nodes.map((node, index) => {
    const jitter = random(hash(node.id));
    return { node,
      x: W * (.105 + .79 * halton(index + 1, 2) + (jitter() - .5) * .025),
      y: H * (.505 + (halton(index + 1, 3) - .5) * .19 + (jitter() - .5) * .018),
    };
  });
}

function drawBackgroundStars() {
  const W = state.width, H = state.height;
  for (const star of state.stars) {
    ctx.beginPath();
    ctx.arc(star.x * W, star.y * H, star.radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(203,219,232,${star.alpha})`;
    ctx.fill();
  }
}

function nodeImportance(node) {
  const rank = {
    direction_change: 4.7, milestone: 4.2, decision: 3.8,
    requirement: 3.2, implementation: 2.6, blocker: 2.5,
    verification: 1.9, failed_approach: 1.7,
  };
  return clamp((rank[node.kind] || 2) + (node.impact === "major" ? .5 : 0) +
    (["in_progress", "blocked", "pending_approval"].includes(node.status) ? .25 : 0), 1, 5);
}

function brightStar(x, y, radius, selected = false, gold = false, brightness = 1) {
  const glow = ctx.createRadialGradient(x, y, 0, x, y, radius * 4.4);
  const color = gold ? "236,211,174" : "223,232,236";
  glow.addColorStop(0, `rgba(${color},${selected ? .9 : .34 * brightness})`);
  glow.addColorStop(.18, `rgba(${color},${selected ? .36 : .11 * brightness})`);
  glow.addColorStop(1, `rgba(${color},0)`);
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, radius * 4.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = gold ? `rgba(249,228,196,${brightness})` : `rgba(240,247,249,${brightness})`;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  if (selected) {
    ctx.strokeStyle = "rgba(234,210,169,.48)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(x, y, radius * 4.8, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function normal(rand) {
  return Math.sqrt(-2 * Math.log(Math.max(.00001, rand()))) * Math.cos(2 * Math.PI * rand());
}

function galaxyDust(kind, seed, count) {
  const key = `${kind}:${seed}:${count}`;
  if (state.galaxies.has(key)) return state.galaxies.get(key);
  const rand = random(seed);
  const dust = [];
  for (let i = 0; i < count; i++) {
    let x, y, radius;
    if (kind === "edge") {
      x = clamp(normal(rand) * .39, -.99, .99);
      const taper = Math.max(.12, 1 - Math.abs(x) * .88);
      y = normal(rand) * (.14 * taper + .025) + Math.sin(x * 3.1) * .028;
      radius = Math.abs(x);
    } else if (kind === "elliptical") {
      x = normal(rand) * .38;
      y = normal(rand) * .35;
      radius = Math.hypot(x, y);
    } else {
      const irregular = kind === "irregular";
      radius = Math.sqrt(rand()) * (irregular ? .89 : .98);
      const arms = irregular ? 2 : 4;
      const arm = i % arms;
      const spread = (irregular ? .42 : .19) * (.35 + radius);
      const angle = arm * 2 * Math.PI / arms + radius * (irregular ? 3.7 : 4.4) + normal(rand) * spread;
      x = Math.cos(angle) * radius + normal(rand) * .035;
      y = Math.sin(angle) * radius * (irregular ? .7 : .76) + normal(rand) * .035;
      if (rand() < .24) {
        const diskAngle = rand() * 2 * Math.PI;
        const diskRadius = Math.sqrt(rand()) * .78;
        x = Math.cos(diskAngle) * diskRadius;
        y = Math.sin(diskAngle) * diskRadius * .72;
        radius = diskRadius;
      }
    }
    if (Math.abs(x) > 1.08 || Math.abs(y) > 1.08) continue;
    const core = radius < .23;
    const palette = core && rand() < .56 ? "238,208,178" :
      rand() < .42 ? "151,178,205" : rand() < .65 ? "199,210,219" : "93,123,158";
    const alpha = (kind === "elliptical" ? .18 : .19) + rand() * (core ? .62 : .57);
    dust.push({ x, y, size: rand() < .045 ? 1.55 : .58 + rand() * .75,
      color: `rgba(${palette},${(Math.round(alpha * 8) / 8).toFixed(3)})` });
  }
  dust.sort((a, b) => a.color.localeCompare(b.color));
  state.galaxies.set(key, dust);
  return dust;
}

function paintStructure(kind, width, height) {
  if (kind === "spiral" || kind === "irregular") {
    const arms = kind === "spiral" ? 4 : 2;
    const segments = [[.18, .33], [.36, .51], [.54, .69], [.72, .9]];
    for (let arm = 0; arm < arms; arm++) {
      for (let section = 0; section < segments.length; section++) {
        const [start, end] = segments[section];
        ctx.beginPath();
        for (let step = 0; step <= 22; step++) {
          const radius = start + (end - start) * step / 22;
          const angle = arm * Math.PI * 2 / arms + radius * (kind === "spiral" ? 4.4 : 3.7);
          const x = Math.cos(angle) * radius * width * .5;
          const y = Math.sin(angle) * radius * height * .38;
          if (!step) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.lineCap = "round";
        ctx.lineWidth = clamp(width / 780, .5, 1.2) * (22 + section * 4);
        ctx.strokeStyle = `rgba(129,160,195,${.035 + (section % 2) * .015})`;
        ctx.stroke();
      }
    }
  } else if (kind === "edge") {
    const lane = ctx.createLinearGradient(-width * .5, 0, width * .5, 0);
    lane.addColorStop(0, "rgba(0,0,0,0)");
    lane.addColorStop(.2, "rgba(2,5,11,.2)");
    lane.addColorStop(.5, "rgba(2,5,11,.34)");
    lane.addColorStop(.8, "rgba(2,5,11,.2)");
    lane.addColorStop(1, "rgba(0,0,0,0)");
    ctx.beginPath();
    ctx.moveTo(-width * .49, -height * .01);
    ctx.bezierCurveTo(-width * .18, height * .025, width * .18, -height * .03, width * .49, height * .015);
    ctx.lineWidth = clamp(height * .035, 3, 10);
    ctx.strokeStyle = lane;
    ctx.stroke();
  }
}

function paintGalaxy(galaxy, seed, opacity = 1) {
  const point = screenPoint(galaxy.x, galaxy.y);
  const width = galaxy.width * state.camera.scale;
  const height = galaxy.height * state.camera.scale;
  const kind = galaxy.kind;
  const count = kind === "spiral" ? 30000 : kind === "edge" ? 12000 : 9000;
  ctx.save();
  ctx.translate(point.x, point.y);
  ctx.rotate(galaxy.angle);
  ctx.globalAlpha = opacity;
  const haze = ctx.createRadialGradient(0, 0, 0, 0, 0, width * .52);
  haze.addColorStop(0, "rgba(160,174,190,.1)");
  haze.addColorStop(.35, "rgba(64,91,124,.05)");
  haze.addColorStop(1, "rgba(38,64,95,0)");
  ctx.save();
  ctx.scale(1, height / width);
  ctx.fillStyle = haze;
  ctx.beginPath();
  ctx.arc(0, 0, width * .52, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  if (kind !== "edge") paintStructure(kind, width, height);
  const dust = galaxyDust(kind, seed, count);
  let previousColor = "";
  for (const particle of dust) {
    if (particle.color !== previousColor) {
      ctx.fillStyle = particle.color;
      previousColor = particle.color;
    }
    const size = particle.size * clamp(state.camera.scale, .7, 2);
    ctx.fillRect(particle.x * width * .5, particle.y * height * .5, size, size);
  }
  if (kind === "edge") paintStructure(kind, width, height);
  const coreRadius = Math.min(width * (kind === "edge" ? .11 : .09), height * (kind === "edge" ? .18 : .13));
  const core = ctx.createRadialGradient(0, 0, 0, 0, 0, coreRadius * 2.7);
  core.addColorStop(0, "rgba(255,237,214,.66)");
  core.addColorStop(.16, "rgba(236,204,175,.39)");
  core.addColorStop(.55, "rgba(147,162,180,.08)");
  core.addColorStop(1, "rgba(91,124,156,0)");
  ctx.save();
  ctx.scale(kind === "edge" ? 2.6 : 1.35, kind === "edge" ? .46 : .88);
  ctx.fillStyle = core;
  ctx.beginPath();
  ctx.arc(0, 0, coreRadius * 2.7, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.restore();
}

function drawUniverse() {
  const image = state.universeImage;
  if (!image?.complete || !image.naturalWidth) return;
  const bounds = universeBounds();
  const exposedEdge = bounds.y > 0 || bounds.y + bounds.height < state.height ||
    bounds.x > 0 || bounds.x + bounds.width < state.width;
  ctx.drawImage(exposedEdge ? maskedUniverseImage() : image,
    bounds.x, bounds.y, bounds.width, bounds.height);
  // The supplied reference has example interface text baked into its pixels.
  // Cover only those small regions; the galaxies and their original colors stay intact.
  for (const region of [
    { x: .01, y: .018, w: .34, h: .062 },
    ...referenceSlots.map(slot => ({ x: slot.x - .015, y: slot.y - .034, w: slot.width + .04, h: .105 })),
  ]) {
    const x = bounds.x + region.x * bounds.width;
    const y = bounds.y + region.y * bounds.height;
    const width = region.w * bounds.width;
    const height = region.h * bounds.height;
    ctx.save();
    ctx.translate(x + width / 2, y + height / 2);
    ctx.scale(width / 2, height / 2);
    const cover = ctx.createRadialGradient(0, 0, .1, 0, 0, 1);
    cover.addColorStop(0, "rgba(0,0,0,1)");
    cover.addColorStop(.72, "rgba(0,0,0,.99)");
    cover.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = cover;
    ctx.fillRect(-1, -1, 2, 2);
    ctx.restore();
  }
}

function maskedUniverseImage() {
  if (state.maskedUniverse) return state.maskedUniverse;
  const image = state.universeImage;
  const layer = document.createElement("canvas");
  layer.width = image.naturalWidth;
  layer.height = image.naturalHeight;
  const layerCtx = layer.getContext("2d");
  layerCtx.drawImage(image, 0, 0);
  layerCtx.globalCompositeOperation = "destination-in";
  const edge = Math.min(135, layer.height * .14);
  const vertical = layerCtx.createLinearGradient(0, 0, 0, layer.height);
  vertical.addColorStop(0, "rgba(0,0,0,0)");
  vertical.addColorStop(edge / layer.height, "rgba(0,0,0,1)");
  vertical.addColorStop(1 - edge / layer.height, "rgba(0,0,0,1)");
  vertical.addColorStop(1, "rgba(0,0,0,0)");
  layerCtx.fillStyle = vertical;
  layerCtx.fillRect(0, 0, layer.width, layer.height);
  const side = Math.min(75, layer.width * .045);
  const horizontal = layerCtx.createLinearGradient(0, 0, layer.width, 0);
  horizontal.addColorStop(0, "rgba(0,0,0,0)");
  horizontal.addColorStop(side / layer.width, "rgba(0,0,0,1)");
  horizontal.addColorStop(1 - side / layer.width, "rgba(0,0,0,1)");
  horizontal.addColorStop(1, "rgba(0,0,0,0)");
  layerCtx.fillStyle = horizontal;
  layerCtx.fillRect(0, 0, layer.width, layer.height);
  state.maskedUniverse = layer;
  return layer;
}

function drawProject() {
  const W = state.width, H = state.height;
  paintGalaxy({ x: W * .5, y: H * .53, width: W * 1.45, height: H * .48,
    kind: "edge", angle: .018 }, hash(state.currentId || "project"), .58);
  const positions = projectNodes();
  const byId = new Map(positions.map(position => [position.node.id, position]));
  const chosen = state.selected;
  const edges = [];
  const seenEdges = new Set();
  for (const position of positions) {
    for (const relatedId of [...(position.node.predecessors || []), ...(position.node.affects || [])]) {
      const related = byId.get(relatedId);
      if (!related) continue;
      const edgeId = [position.node.id, relatedId].sort().join(":");
      if (seenEdges.has(edgeId)) continue;
      seenEdges.add(edgeId);
      edges.push({ from: position, to: related });
    }
  }
  const drawEdge = (edge, active) => {
      const from = screenPoint(edge.from.x, edge.from.y);
      const to = screenPoint(edge.to.x, edge.to.y);
      ctx.strokeStyle = active ? "rgba(246,220,178,.9)" : "rgba(197,212,225,.24)";
      ctx.lineWidth = active ? 1.7 : .85;
      ctx.shadowColor = active ? "rgba(244,207,154,.8)" : "transparent";
      ctx.shadowBlur = active ? 9 : 0;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
  };
  edges.forEach(edge => drawEdge(edge, false));
  if (chosen) edges.filter(edge => edge.from.node.id === chosen || edge.to.node.id === chosen)
    .forEach(edge => drawEdge(edge, true));
  ctx.shadowBlur = 0;
  for (const position of positions) {
    const point = screenPoint(position.x, position.y);
    const active = state.selected === position.node.id || state.hovered === position.node.id;
    const gold = position.node.kind === "decision" || position.node.kind === "milestone";
    const importance = nodeImportance(position.node);
    brightStar(point.x, point.y, (active ? 1.18 : 1) * (1.25 + importance * .58) * clamp(state.camera.scale, .75, 2),
      active, gold, .63 + importance * .074);
  }
  if (!positions.length) {
    ctx.fillStyle = "rgba(218,225,229,.68)";
    ctx.font = '15px Georgia, "Noto Serif SC", serif';
    ctx.textAlign = "center";
    ctx.fillText("这片星云正在等待第一颗记忆星星", W / 2, H * .56);
    ctx.textAlign = "start";
  }
}

function frame(time) {
  if (time - state.lastFrame < 30) { requestAnimationFrame(frame); return; }
  const dt = Math.min(80, time - (state.lastFrame || time));
  state.lastFrame = time;
  if (!motionPreference.matches && time - state.lastInteraction > 2600 && !state.pointer?.dragging) {
    state.driftPhase += dt * .00008;
  }
  const ratio = canvas.width / (state.width || 1);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.fillStyle = state.scene === "universe" ? "#000" : "#03060c";
  ctx.fillRect(0, 0, state.width, state.height);
  drawBackgroundStars();
  if (state.scene === "universe") drawUniverse(); else drawProject();
  if (state.scene === "universe") positionGalaxyLabels();
  requestAnimationFrame(frame);
}

function hitNode(x, y) {
  return projectNodes().find(position => {
    const point = screenPoint(position.x, position.y);
    return Math.hypot(x - point.x, y - point.y) < 14;
  })?.node || null;
}

function resetView() {
  state.camera = { x: 0, y: 0, scale: 1 };
  state.driftPhase = 0;
  touch();
}

function selectNode(id) {
  state.selected = id;
  state.scene = "project";
  updateLabels();
  updateToolbar();
  renderCard();
}

function renderCard() {
  card.replaceChildren();
  const node = state.current?.nodes.find(item => item.id === state.selected);
  if (!node || state.scene !== "project") { card.classList.add("hidden"); return; }
  const head = el("div", "node-card-head");
  const top = el("div");
  top.append(el("div", "kicker", `${kindNames[node.kind] || node.kind} · ${node.id}`), el("h2", "", node.title));
  const close = el("button", "close-button", "×");
  close.setAttribute("aria-label", "关闭节点详情");
  close.addEventListener("click", () => { state.selected = null; renderCard(); });
  head.append(top, close);
  card.append(head, el("p", "", node.summary));
  const tags = el("div", "tag-row");
  for (const value of [node.phase, statusNames[node.status] || node.status, evidenceNames[node.evidence_level] || node.evidence_level, `修订 ${node.revision}`]) {
    tags.append(el("span", "tag", value));
  }
  card.append(tags);
  for (const [label, value] of [["选择原因", node.rationale], ["结果", node.outcome], ["下一步", node.next_steps?.join("；")]]) {
    if (value) card.append(el("div", "detail-label", label), el("p", "", value));
  }
  if (node.predecessors?.length) card.append(el("div", "detail-label", "前置节点"), el("p", "", node.predecessors.join(" · ")));
  card.classList.remove("hidden");
}

function metric(label, number) {
  const item = el("div", "metric-card");
  item.append(el("strong", "", number), el("span", "", label));
  return item;
}

function nodeRow(node, extra = "") {
  const row = el("button", "item-row");
  row.append(el("span", "meta", `${node.phase} · ${kindNames[node.kind] || node.kind} · ${statusNames[node.status] || node.status}${extra}`),
    el("strong", "", node.title));
  row.addEventListener("click", () => { state.panel = null; panel.classList.add("hidden"); selectNode(node.id); });
  return row;
}

function section(title, nodes, empty = "暂无记录") {
  panelBody.append(el("h3", "", title));
  if (!nodes.length) { panelBody.append(el("p", "quiet", empty)); return; }
  const list = el("div", "item-list");
  nodes.forEach(node => list.append(nodeRow(node)));
  panelBody.append(list);
}

function renderProgress() {
  const nodes = state.current.nodes;
  const counts = status => nodes.filter(node => node.status === status).length;
  const grid = el("div", "metric-grid");
  grid.append(metric("已完成", counts("completed")), metric("进行中", counts("in_progress")),
    metric("待开发", counts("planned")), metric("受阻 / 待确认", counts("blocked") + counts("pending_approval")));
  panelBody.append(grid);
  section("正在推进", nodes.filter(node => ["in_progress", "blocked", "pending_approval"].includes(node.status)));
  section("待开发需求", nodes.filter(node => node.kind === "requirement" && node.status === "planned"));
  section("最近完成", nodes.filter(node => node.status === "completed").slice(-8).reverse());
}

function renderFlow() {
  panelBody.append(el("p", "", "选择一颗节点星星时，与它相连的开发路径会亮起。这里按项目阶段列出完整节点。"));
  const phases = [...new Set(state.current.nodes.map(node => node.phase))];
  phases.forEach(phase => section(phase, state.current.nodes.filter(node => node.phase === phase)));
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("zh-CN", { year: "numeric", month: "short", day: "numeric" });
}

function renderTimeline() {
  panelBody.append(el("p", "", "按照发生时间回看项目发展；点击任意记录定位到对应星星。"));
  const list = el("div", "item-list");
  [...state.current.nodes].reverse().forEach(node => list.append(nodeRow(node, ` · ${formatTime(node.occurred_at)}`)));
  panelBody.append(list);
}

function renderSearch() {
  const input = el("input", "field");
  input.type = "search";
  input.placeholder = "搜索标题、结论、原因或下一步";
  input.setAttribute("aria-label", "搜索节点");
  const kind = el("select", "select");
  kind.setAttribute("aria-label", "按节点类型筛选");
  kind.append(new Option("全部类型", ""));
  Object.entries(kindNames).forEach(([value, label]) => kind.append(new Option(label, value)));
  const phase = el("select", "select");
  phase.setAttribute("aria-label", "按项目阶段筛选");
  phase.append(new Option("全部阶段", ""));
  [...new Set(state.current.nodes.map(node => node.phase))].forEach(value => phase.append(new Option(value, value)));
  const filters = el("div", "filter-row");
  filters.append(kind, phase);
  const results = el("div", "item-list");
  const count = el("p", "quiet");
  const update = () => {
    const term = input.value.trim().toLocaleLowerCase();
    const matches = state.current.nodes.filter(node => {
      if (kind.value && node.kind !== kind.value) return false;
      if (phase.value && node.phase !== phase.value) return false;
      const content = [node.title, node.summary, node.rationale, node.outcome, ...(node.next_steps || [])].join(" ").toLocaleLowerCase();
      return !term || content.includes(term);
    });
    count.textContent = `找到 ${matches.length} 个节点`;
    results.replaceChildren(...matches.map(node => nodeRow(node)));
  };
  [input, kind, phase].forEach(control => control.addEventListener("input", update));
  panelBody.append(input, filters, count, results);
  update();
  setTimeout(() => input.focus(), 0);
}

function renderHandoff() {
  const meta = state.current.meta;
  panelBody.append(el("h3", "", "项目目标"), el("p", "", meta.goal || "尚未记录"),
    el("h3", "", "范围"), el("p", "", meta.scope || "尚未记录"),
    el("div", "divider"), el("h3", "", "交接说明"), el("pre", "markdown-text", state.current.handoff_text));
}

function renderProjects() {
  panelBody.append(el("p", "", "添加已启用开发记忆的本地项目。宇宙只保存项目路径，每个项目的记忆仍留在自己的目录中。"));
  const input = el("input", "field");
  input.placeholder = "项目文件夹的完整路径";
  input.setAttribute("aria-label", "项目文件夹路径");
  const add = el("button", "primary-button", "添加");
  const form = el("form", "project-form");
  form.append(input, add);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!input.value.trim()) return;
    add.disabled = true;
    try {
      const project = await api("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: input.value.trim() }) });
      await loadProjects();
      await chooseProject(project.id);
      toast("项目已加入宇宙");
    } catch (error) { toast(error.message); }
    finally { add.disabled = false; }
  });
  panelBody.append(el("h3", "", "添加项目"), form, el("div", "divider"), el("h3", "", "已连接的项目"));
  if (!state.projects.length) panelBody.append(el("p", "quiet", "还没有项目。先使用 memory.py init 初始化项目，再输入项目路径。"));
  for (const project of state.projects) {
    const box = el("div", "item-row");
    box.append(el("strong", "", project.name), el("span", "project-path", project.path));
    if (project.error) box.append(el("span", "summary", project.error));
    else box.append(el("span", "summary", `${project.node_count} 条记忆 · ${project.completed} 条已完成`));
    const actions = el("div", "project-actions");
    const open = el("button", "ghost-button", "进入星云");
    open.disabled = Boolean(project.error);
    open.addEventListener("click", () => chooseProject(project.id).catch(error => toast(error.message)));
    const remove = el("button", "ghost-button", "从宇宙移除");
    remove.addEventListener("click", async () => {
      if (!window.confirm(`从宇宙列表移除“${project.name}”？项目文件不会删除。`)) return;
      try {
        await api(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
        await loadProjects();
        renderPanel();
        toast("已从宇宙列表移除");
      } catch (error) { toast(error.message); }
    });
    actions.append(open, remove);
    box.append(actions);
    panelBody.append(box);
  }
}

function renderPanel() {
  if (!state.panel) { panel.classList.add("hidden"); updateToolbar(); return; }
  panel.classList.remove("hidden");
  const titles = { progress: "项目进度", flow: "开发流程", timeline: "时间线", search: "搜索筛选", handoff: "交接资料", projects: "项目管理", settings: "设置" };
  document.querySelector("#panel-kicker").textContent = ["projects", "settings"].includes(state.panel) ? "WORKSPACE" : (state.current?.project.name || "PROJECT");
  document.querySelector("#panel-title").textContent = titles[state.panel];
  panelBody.replaceChildren();
  if (state.panel === "projects") renderProjects();
  else if (state.panel === "settings") {
    panelBody.append(el("h3", "", "浏览方式"),
      el("p", "", "鼠标滚轮缩放宇宙，拖动画面调整视角。停止操作后，星空会缓慢移动。"),
      el("h3", "", "项目"),
      el("p", "", "在项目管理中连接本地项目；封面会显示真实项目名称。"));
    const projects = el("button", "primary-button", "打开项目管理");
    projects.addEventListener("click", () => { state.panel = "projects"; renderPanel(); });
    panelBody.append(projects);
  }
  else if (!state.current) panelBody.append(el("p", "", "先从宇宙中选择一个项目。"));
  else ({ progress: renderProgress, flow: renderFlow, timeline: renderTimeline, search: renderSearch, handoff: renderHandoff })[state.panel]?.();
  updateToolbar();
}

async function toolbarAction(action) {
  touch();
  if (action === "reset") { resetView(); return; }
  if (action === "universe") {
    state.scene = "universe"; state.panel = null; state.selected = null;
    resetView(); updateLabels(); renderPanel(); renderCard(); return;
  }
  if (action === "project") {
    if (!state.currentId) { state.panel = "projects"; renderPanel(); return; }
    if (!state.current) await loadCurrent();
    state.scene = "project"; state.panel = null; resetView();
    updateLabels(); renderPanel(); renderCard(); return;
  }
  if (action !== "projects" && !state.current && state.currentId) await loadCurrent();
  state.panel = state.panel === action ? null : action;
  renderPanel();
}

toolbar.addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (button) toolbarAction(button.dataset.action).catch(error => toast(error.message));
});
coverNav.addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (button) toolbarAction(button.dataset.action).catch(error => toast(error.message));
});
document.querySelector("#panel-close").addEventListener("click", () => { state.panel = null; renderPanel(); });

canvas.addEventListener("pointerdown", event => {
  canvas.setPointerCapture(event.pointerId);
  state.pointer = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, dragging: false };
  touch();
});
canvas.addEventListener("pointermove", event => {
  touch();
  if (state.pointer) {
    const dx = event.clientX - state.pointer.x, dy = event.clientY - state.pointer.y;
    if (Math.hypot(event.clientX - state.pointer.startX, event.clientY - state.pointer.startY) > 4) state.pointer.dragging = true;
    if (state.pointer.dragging) {
      state.camera.x += dx; state.camera.y += dy;
      if (state.scene === "universe") universeBounds();
    }
    state.pointer.x = event.clientX; state.pointer.y = event.clientY;
  } else {
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    if (state.scene === "project") state.hovered = hitNode(x, y)?.id || null;
    canvas.style.cursor = state.hovered ? "pointer" : "grab";
  }
});
canvas.addEventListener("pointerup", event => {
  if (!state.pointer) return;
  const wasDragging = state.pointer.dragging;
  state.pointer = null;
  if (wasDragging) return;
  const bounds = canvas.getBoundingClientRect();
  const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
  if (state.scene === "project") {
    const node = hitNode(x, y);
    state.selected = node?.id || null;
    renderCard();
  }
});
canvas.addEventListener("pointercancel", () => { state.pointer = null; });
canvas.addEventListener("wheel", event => {
  event.preventDefault(); touch();
  const bounds = canvas.getBoundingClientRect();
  const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
  const before = worldPoint(x, y);
  state.camera.scale = clamp(state.camera.scale * Math.exp(-clamp(event.deltaY, -180, 180) * .0013),
    state.scene === "universe" ? 1 : .55, 3.5);
  const offset = drift();
  state.camera.x = x - (before.x - state.width / 2) * state.camera.scale - state.width / 2 - offset.x;
  state.camera.y = y - (before.y - state.height / 2) * state.camera.scale - state.height / 2 - offset.y;
  if (state.scene === "universe") universeBounds();
}, { passive: false });
window.addEventListener("pointermove", touch);
window.addEventListener("resize", resize);

async function start() {
  resize();
  state.universeImage = new Image();
  state.universeImage.src = "/assets/universe-reference.png";
  requestAnimationFrame(frame);
  try {
    await loadProjects();
    if (state.currentId) await loadCurrent();
    else { state.panel = "projects"; renderPanel(); }
  } catch (error) { toast(error.message); }
  setInterval(async () => {
    try {
      await loadProjects();
      if (state.currentId) await loadCurrent();
      if (state.panel && state.panel !== "search") renderPanel();
      if (state.selected) renderCard();
    } catch (error) { toast(error.message); }
  }, 15000);
}

start();
