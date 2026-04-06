'use strict';

(() => {
  function startBackgroundAnimation() {
    const bgElement = document.getElementById('bg-animation');
    if (!bgElement) {
      return;
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion) {
      return;
    }

    const state = {
      pos1: { x: -10, y: -20, vx: 0, vy: 0 },
      pos2: { x: 110, y: 0, vx: 0, vy: 0 },
      pos3: { x: 50, y: 120, vx: 0, vy: 0 },
    };

    const maxSpeed = 0.8;
    const directionChangeChance = 0.05;
    const bounds = { minX: -10, maxX: 110, minY: -10, maxY: 110 };

    function updatePosition(pos) {
      if (Math.random() < directionChangeChance) {
        pos.vx += (Math.random() - 0.5) * 0.3;
        pos.vy += (Math.random() - 0.5) * 0.3;
      }

      const speed = Math.hypot(pos.vx, pos.vy);
      if (speed > maxSpeed) {
        pos.vx = (pos.vx / speed) * maxSpeed;
        pos.vy = (pos.vy / speed) * maxSpeed;
      }

      pos.x += pos.vx;
      pos.y += pos.vy;

      if (pos.x < bounds.minX || pos.x > bounds.maxX) {
        pos.vx *= -0.9;
        pos.x = Math.max(bounds.minX, Math.min(bounds.maxX, pos.x));
      }
      if (pos.y < bounds.minY || pos.y > bounds.maxY) {
        pos.vy *= -0.9;
        pos.y = Math.max(bounds.minY, Math.min(bounds.maxY, pos.y));
      }

      pos.vx *= 0.998;
      pos.vy *= 0.998;
    }

    function frame() {
      updatePosition(state.pos1);
      updatePosition(state.pos2);
      updatePosition(state.pos3);

      bgElement.style.background = `
        radial-gradient(1200px 800px at ${state.pos1.x}% ${state.pos1.y}%, rgba(0, 164, 220, 0.32) 0%, rgba(0, 0, 0, 0) 55%),
        radial-gradient(1000px 700px at ${state.pos2.x}% ${state.pos2.y}%, rgba(255, 193, 7, 0.28) 0%, rgba(0, 0, 0, 0) 52%),
        radial-gradient(1100px 900px at ${state.pos3.x}% ${state.pos3.y}%, rgba(170, 92, 195, 0.25) 0%, rgba(0, 0, 0, 0) 50%)
      `;

      window.requestAnimationFrame(frame);
    }

    window.requestAnimationFrame(frame);
  }

  window.addEventListener('load', startBackgroundAnimation);
})();
