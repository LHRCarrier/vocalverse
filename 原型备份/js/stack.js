/* Stack：matter-js 2D 物理沙盒，可拖拽芯片 */
(() => {
  const shell = document.querySelector("[data-stack-shell]");
  if (!shell || !window.Matter) return;

  const canvas = shell.querySelector("[data-stack-canvas]");
  const measure = shell.querySelector("[data-stack-measure]");
  const resetBtn = shell.querySelector("[data-stack-reset]");
  const chipEls = Array.from(shell.querySelectorAll("[data-stack-chip]"));
  const WALL_PAD = 16;
  const CHIP_RADIUS = 14;

  let cleanup = () => {};

  const boot = () => {
    const { Engine, Runner, World, Bodies, Body, Mouse, MouseConstraint, Events } = window.Matter;

    const children = Array.from(measure.children);
    const dims = children.map((el) => {
      const r = el.getBoundingClientRect();
      return { w: Math.max(80, r.width), h: Math.max(28, r.height) };
    });

    let width = canvas.clientWidth;
    let height = canvas.clientHeight;

    const engine = Engine.create();
    engine.gravity.y = 1;
    const world = engine.world;

    const wallThickness = 400;
    const floor = Bodies.rectangle(
      width / 2,
      height - WALL_PAD + wallThickness / 2,
      width * 3,
      wallThickness,
      { isStatic: true }
    );
    const leftWall = Bodies.rectangle(
      WALL_PAD - wallThickness / 2,
      height / 2,
      wallThickness,
      height * 4,
      { isStatic: true }
    );
    const rightWall = Bodies.rectangle(
      width - WALL_PAD + wallThickness / 2,
      height / 2,
      wallThickness,
      height * 4,
      { isStatic: true }
    );
    World.add(world, [floor, leftWall, rightWall]);

    const states = chipEls.map((el, i) => {
      const dim = dims[i] || { w: 120, h: 36 };
      const halfW = dim.w / 2;
      const minX = WALL_PAD + halfW + 4;
      const maxX = width - WALL_PAD - halfW - 4;
      const x = minX + Math.random() * Math.max(1, maxX - minX);
      const y = -80 - i * 60 - Math.random() * 120;
      const body = Bodies.rectangle(x, y, dim.w, dim.h, {
        chamfer: { radius: CHIP_RADIUS },
        restitution: 0.35,
        friction: 0.5,
        frictionAir: 0.025,
        density: 0.0018,
        angle: (Math.random() - 0.5) * 0.4,
      });
      World.add(world, body);
      return { el, body, width: dim.w, height: dim.h };
    });

    const mouse = Mouse.create(canvas);
    /* 移除 matter 默认的 wheel 监听，避免劫持页面滚动 */
    if (mouse.element && mouse.mousewheel) {
      mouse.element.removeEventListener("wheel", mouse.mousewheel);
    }
    const mouseConstraint = MouseConstraint.create(engine, {
      mouse,
      constraint: {
        stiffness: 0.2,
        damping: 0.2,
        render: { visible: false },
      },
    });
    World.add(world, mouseConstraint);
    Events.on(mouseConstraint, "startdrag", () => {
      canvas.style.cursor = "grabbing";
    });
    Events.on(mouseConstraint, "enddrag", () => {
      canvas.style.cursor = "grab";
    });

    const runner = Runner.create();
    Runner.run(runner, engine);

    let raf = 0;
    const tick = () => {
      states.forEach((s) => {
        s.el.style.transform = `translate3d(${s.body.position.x - s.width / 2}px, ${s.body.position.y - s.height / 2}px, 0) rotate(${s.body.angle}rad)`;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onResize = () => {
      const newW = canvas.clientWidth;
      const newH = canvas.clientHeight;
      if (newW === width && newH === height) return;
      Body.setPosition(floor, {
        x: newW / 2,
        y: newH - WALL_PAD + wallThickness / 2,
      });
      Body.setPosition(leftWall, {
        x: WALL_PAD - wallThickness / 2,
        y: newH / 2,
      });
      Body.setPosition(rightWall, {
        x: newW - WALL_PAD + wallThickness / 2,
        y: newH / 2,
      });
      width = newW;
      height = newH;
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(canvas);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      Runner.stop(runner);
      World.clear(world, false);
      Engine.clear(engine);
    };
  };

  cleanup = boot();

  resetBtn.addEventListener("click", () => {
    cleanup();
    cleanup = boot();
  });
})();