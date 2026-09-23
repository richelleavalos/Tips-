/**
 * Recurso global compartido por distintas vistas de Tips: motion runtime. Debe permanecer independiente de un rol concreto.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
const root = document.documentElement;
const body = document.body;
const motionSelector = [
  ".hero-copy > *", ".hero-canvas", ".architecture-hero > *", ".dual-feature > *",
  ".section-head", ".project-card", ".mini-product", ".portfolio-card", ".shop-card",
  ".service-lines article", ".process-grid article", ".quote-banner-inner > *",
  ".quote-heading > *", ".quote-layout > *", ".project-top > *", ".project-layout > *",
  ".checkout-layout > *", ".demo-alert", ".auth-shell", ".account-intro > *", ".footer-grid > *",
  ".admin-page-head > *", ".admin-metric", ".admin-card", ".admin-toolbar",
  ".admin-table tbody tr", ".admin-alert", ".admin-nav-group", ".admin-top-actions > *",
  ".user-head > *", ".user-stat", ".user-card", ".user-order", ".user-nav a"
].join(",");

let sequence = 0;
let mutationFrame = 0;
const pendingRoots = new Set();

const revealObserver = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    entry.target.classList.add("motion-in");
    revealObserver.unobserve(entry.target);
    animateCounter(entry.target);
  }
}, { rootMargin: "80px 0px -6%", threshold: 0.06 });

function animateCounter(scope) {
  const targets = scope.matches?.(".admin-metric strong,.user-stat strong")
    ? [scope]
    : [...scope.querySelectorAll?.(".admin-metric strong,.user-stat strong") || []];
  for (const target of targets) {
    if (target.dataset.motionCounted || !/^\d+$/.test(target.textContent.trim())) continue;
    target.dataset.motionCounted = "true";
    const finish = Number(target.textContent);
    const start = performance.now();
    const tick = now => {
      const progress = Math.min(1, (now - start) / 760);
      target.textContent = String(Math.round(finish * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
}

function prepareImage(image) {
  if (image.closest(".topbar,.admin-side-brand,.user-brand,.footer")) return;
  if (!image.hasAttribute("loading")) image.loading = "lazy";
  if (!image.hasAttribute("decoding")) image.decoding = "async";
  image.addEventListener("load", () => image.classList.add("motion-image-ready"), { once: true });
  if (image.complete) image.classList.add("motion-image-ready");
}

function prepareNode(node) {
  if (!(node instanceof Element)) return;
  const candidates = node.matches(motionSelector) ? [node] : [...node.querySelectorAll(motionSelector)];
  for (const candidate of candidates) {
    if (candidate.dataset.motionPrepared) continue;
    candidate.dataset.motionPrepared = "true";
    candidate.style.setProperty("--motion-delay", `${Math.min(sequence % 7, 6) * 48}ms`);
    candidate.classList.add("motion-item", `motion-variant-${sequence % 4}`);
    sequence += 1;
    const rect = candidate.getBoundingClientRect();
    if (rect.top < innerHeight * 0.94 && rect.bottom > 0) {
      requestAnimationFrame(() => {
        candidate.classList.add("motion-in");
        animateCounter(candidate);
      });
    } else {
      revealObserver.observe(candidate);
    }
  }
  if (node.matches("img")) prepareImage(node);
  node.querySelectorAll("img").forEach(prepareImage);
}

function flushMutations() {
  mutationFrame = 0;
  for (const node of pendingRoots) prepareNode(node);
  pendingRoots.clear();
}

const mutationObserver = new MutationObserver(records => {
  for (const record of records) {
    for (const node of record.addedNodes) if (node instanceof Element) pendingRoots.add(node);
  }
  if (!mutationFrame) mutationFrame = requestAnimationFrame(flushMutations);
});

function addRipple(event) {
  const button = event.target.closest("button,.btn,.admin-btn,.user-btn");
  if (!button || button.disabled) return;
  const rect = button.getBoundingClientRect();
  const ripple = document.createElement("span");
  ripple.className = "motion-ripple";
  ripple.style.left = `${event.clientX - rect.left}px`;
  ripple.style.top = `${event.clientY - rect.top}px`;
  button.append(ripple);
  ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
}

function enableParallax() {
  if (!matchMedia("(min-width: 900px) and (pointer: fine)").matches) return;
  const targets = [...document.querySelectorAll(".hero-canvas,.architecture-board,.theme-preview")];
  targets.forEach(target => target.classList.add("motion-parallax"));
  let frame = 0;
  let point = { x: innerWidth / 2, y: innerHeight / 2 };
  window.addEventListener("pointermove", event => {
    point = { x: event.clientX, y: event.clientY };
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const x = ((point.x / innerWidth) - .5) * 7;
      const y = ((point.y / innerHeight) - .5) * 7;
      targets.forEach(target => {
        target.style.setProperty("--motion-x", `${x.toFixed(2)}px`);
        target.style.setProperty("--motion-y", `${y.toFixed(2)}px`);
      });
    });
  }, { passive: true });
}

function enablePageTransitions() {
  document.addEventListener("click", event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
    const href = link.getAttribute("href") || "";
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
    const destination = new URL(link.href, location.href);
    if (destination.origin !== location.origin || destination.href === location.href) return;
    event.preventDefault();
    body.classList.add("motion-page-exit");
    setTimeout(() => { location.href = destination.href; }, 230);
  });
  window.addEventListener("pageshow", () => body.classList.remove("motion-page-exit"));
}

root.classList.add("motion-enabled");
body.classList.add("motion-runtime-ready");
prepareNode(body);
mutationObserver.observe(body, { childList: true, subtree: true });
document.addEventListener("pointerdown", addRipple, { passive: true });
enableParallax();
enablePageTransitions();
requestAnimationFrame(() => body.classList.add("motion-page-enter"));
