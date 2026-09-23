/**
 * Recurso global compartido por distintas vistas de Tips: motion loader. Debe permanecer independiente de un rol concreto.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";

  const localPreview = ["127.0.0.1", "localhost"].includes(location.hostname)
    && new URLSearchParams(location.search).get("motion-preview") === "1";
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches && !localPreview) {
    document.documentElement.classList.add("motion-reduced");
    return;
  }

  const loadMotion = () => {
    if (document.documentElement.dataset.motionRequested) return;
    document.documentElement.dataset.motionRequested = "true";

    const styles = document.createElement("link");
    styles.rel = "stylesheet";
    styles.href = "/frontend/global/css/motion.css?v=20260923-5";
    styles.onload = () => document.documentElement.classList.add("motion-styles-ready");
    document.head.append(styles);

    import("/frontend/global/js/motion-runtime.js?v=20260923-5").catch(() => {
      document.documentElement.classList.add("motion-load-failed");
    });
  };

  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(loadMotion, { timeout: 900 });
  } else {
    window.setTimeout(loadMotion, 120);
  }
  window.setTimeout(loadMotion, 420);
})();
