import { useEffect, useRef } from 'react';

// Fondo interactivo: retícula vectorial en perspectiva y una constelación de nodos que
// reacciona al puntero (se aparta, se ilumina y se conecta a la mira). Un clic lanza una
// onda de radar. Es decorativo: no intercepta clics y queda fijo con movimiento reducido.
const VIOLET = '155,124,255';
const ACID = '230,255,77';
const CORAL = '255,106,61';
const PALETTE = [VIOLET, VIOLET, VIOLET, ACID, CORAL];
const LINK = 124;
const REACH = 190;
const PULSE_MS = 1500;
const PULSE_RADIUS = 460;

function makeNodes(width, height) {
  const count = Math.max(28, Math.min(90, Math.round((width * height) / 21000)));
  return Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    bx: (Math.random() - .5) * 14,
    by: (Math.random() - .5) * 14,
    kx: 0,
    ky: 0,
    color: PALETTE[Math.floor(Math.random() * PALETTE.length)],
    size: Math.random() < .2 ? 3 : 2,
    glow: 0,
  }));
}

export default function VectorField({ dim = false }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    const still = window.matchMedia('(prefers-reduced-motion: reduce)');
    const pointer = { x: 0, y: 0, active: false };
    let width = 0;
    let height = 0;
    let nodes = [];
    let pulses = [];
    let frame = 0;
    let last = 0;
    let travel = 0;

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      nodes = makeNodes(width, height);
      if (still.matches) draw(0, 0);
    }

    function drawGrid() {
      const horizon = height * .6;
      const depth = height - horizon;
      // El punto de fuga sigue un poco al puntero: da sensación de profundidad.
      const vanish = width / 2 + (pointer.active ? (pointer.x - width / 2) * .1 : 0);
      const fade = context.createLinearGradient(0, horizon, 0, height);
      fade.addColorStop(0, `rgba(${VIOLET},0)`);
      fade.addColorStop(1, `rgba(${VIOLET},.34)`);
      context.strokeStyle = fade;
      context.lineWidth = 1;
      context.beginPath();
      const columns = Math.ceil(width / 90) + 6;
      for (let index = -columns; index <= columns; index += 1) {
        context.moveTo(vanish + index * 14, horizon);
        context.lineTo(vanish + index * 190, height);
      }
      context.stroke();
      const rows = 12;
      for (let index = 0; index < rows; index += 1) {
        const near = ((index + travel) % rows) / rows;
        const y = horizon + depth * near * near;
        context.strokeStyle = `rgba(${VIOLET},${(.05 + near * .32).toFixed(3)})`;
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(width, y);
        context.stroke();
      }
      const glow = context.createLinearGradient(0, 0, width, 0);
      glow.addColorStop(0, `rgba(${VIOLET},0)`);
      glow.addColorStop(.5, `rgba(${VIOLET},.5)`);
      glow.addColorStop(1, `rgba(${VIOLET},0)`);
      context.strokeStyle = glow;
      context.beginPath();
      context.moveTo(0, horizon);
      context.lineTo(width, horizon);
      context.stroke();
    }

    function drawReticle(now) {
      const { x, y } = pointer;
      const turn = now / 1400;
      context.strokeStyle = `rgba(${ACID},.75)`;
      context.lineWidth = 1;
      context.beginPath();
      context.arc(x, y, 16, turn, turn + Math.PI * .6);
      context.moveTo(x + 16 * Math.cos(turn + Math.PI), y + 16 * Math.sin(turn + Math.PI));
      context.arc(x, y, 16, turn + Math.PI, turn + Math.PI * 1.6);
      context.stroke();
      context.beginPath();
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dx, dy]) => {
        context.moveTo(x + dx * 24, y + dy * 24);
        context.lineTo(x + dx * 32, y + dy * 32);
      });
      context.stroke();
    }

    function draw(now, delta) {
      context.clearRect(0, 0, width, height);
      drawGrid();

      pulses = pulses.filter((pulse) => now - pulse.start < PULSE_MS);
      pulses.forEach((pulse) => {
        const progress = (now - pulse.start) / PULSE_MS;
        const radius = PULSE_RADIUS * (1 - (1 - progress) ** 2);
        [0, 46].forEach((gap, ring) => {
          if (radius - gap <= 0) return;
          context.strokeStyle = `rgba(${CORAL},${((1 - progress) * (ring ? .35 : .8)).toFixed(3)})`;
          context.lineWidth = ring ? 1 : 1.5;
          context.beginPath();
          context.arc(pulse.x, pulse.y, radius - gap, 0, Math.PI * 2);
          context.stroke();
        });
        nodes.forEach((node) => {
          const dx = node.x - pulse.x;
          const dy = node.y - pulse.y;
          const distance = Math.hypot(dx, dy) || 1;
          if (Math.abs(distance - radius) < 26) {
            node.kx += (dx / distance) * 9;
            node.ky += (dy / distance) * 9;
            node.glow = 1;
          }
        });
      });

      nodes.forEach((node) => {
        if (pointer.active) {
          const dx = node.x - pointer.x;
          const dy = node.y - pointer.y;
          const distance = Math.hypot(dx, dy) || 1;
          if (distance < REACH) {
            const push = (1 - distance / REACH) ** 2 * 260 * delta;
            node.kx += (dx / distance) * push;
            node.ky += (dy / distance) * push;
            node.glow = Math.max(node.glow, 1 - distance / REACH);
          }
        }
        node.x += (node.bx + node.kx) * delta;
        node.y += (node.by + node.ky) * delta;
        const drag = Math.exp(-2.2 * delta);
        node.kx *= drag;
        node.ky *= drag;
        node.glow *= Math.exp(-1.6 * delta);
        if (node.x < -20) node.x = width + 20; else if (node.x > width + 20) node.x = -20;
        if (node.y < -20) node.y = height + 20; else if (node.y > height + 20) node.y = -20;
      });

      context.lineWidth = 1;
      for (let a = 0; a < nodes.length; a += 1) {
        for (let b = a + 1; b < nodes.length; b += 1) {
          const distance = Math.hypot(nodes[a].x - nodes[b].x, nodes[a].y - nodes[b].y);
          if (distance < LINK) {
            const lit = Math.max(nodes[a].glow, nodes[b].glow);
            context.strokeStyle = `rgba(${lit > .25 ? ACID : nodes[a].color},${((1 - distance / LINK) * (.2 + lit * .5)).toFixed(3)})`;
            context.beginPath();
            context.moveTo(nodes[a].x, nodes[a].y);
            context.lineTo(nodes[b].x, nodes[b].y);
            context.stroke();
          }
        }
      }
      nodes.forEach((node) => {
        if (pointer.active) {
          const distance = Math.hypot(node.x - pointer.x, node.y - pointer.y);
          if (distance < REACH) {
            context.strokeStyle = `rgba(${ACID},${((1 - distance / REACH) * .55).toFixed(3)})`;
            context.beginPath();
            context.moveTo(pointer.x, pointer.y);
            context.lineTo(node.x, node.y);
            context.stroke();
          }
        }
        const size = node.size + node.glow * 2;
        context.fillStyle = `rgba(${node.glow > .25 ? ACID : node.color},${(.55 + node.glow * .45).toFixed(3)})`;
        context.fillRect(node.x - size / 2, node.y - size / 2, size, size);
      });
      if (pointer.active) drawReticle(now);
    }

    function tick(now) {
      const delta = Math.min(.05, (now - last) / 1000 || 0);
      last = now;
      travel += delta * .55;
      draw(now, delta);
      frame = requestAnimationFrame(tick);
    }

    function start() {
      cancelAnimationFrame(frame);
      if (still.matches || document.hidden) {
        if (still.matches) draw(0, 0);
        return;
      }
      last = performance.now();
      frame = requestAnimationFrame(tick);
    }

    const move = (event) => { pointer.x = event.clientX; pointer.y = event.clientY; pointer.active = !still.matches; };
    const leave = () => { pointer.active = false; };
    const press = (event) => {
      if (still.matches) return;
      pulses.push({ x: event.clientX, y: event.clientY, start: performance.now() });
      if (pulses.length > 4) pulses.shift();
    };

    resize();
    start();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('pointerdown', press, { passive: true });
    document.addEventListener('pointerleave', leave);
    window.addEventListener('blur', leave);
    document.addEventListener('visibilitychange', start);
    still.addEventListener('change', start);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerdown', press);
      document.removeEventListener('pointerleave', leave);
      window.removeEventListener('blur', leave);
      document.removeEventListener('visibilitychange', start);
      still.removeEventListener('change', start);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="vector-field"
      style={{ opacity: dim ? .5 : 1, transition: 'opacity .6s' }}
      aria-hidden="true"
    />
  );
}
