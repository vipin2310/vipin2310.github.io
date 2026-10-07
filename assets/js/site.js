// Progressive enhancement only: every piece of content is in the static HTML.
(() => {
  const root = document.documentElement;

  // Theme toggle. Follows the OS setting until the visitor picks one; the choice is remembered per browser.
  const dark = () => root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.querySelector(".theme")?.addEventListener("click", () => {
    const next = dark() ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) { /* storage blocked: still works for this visit */ }
  });

  // Switchable figure views (all views stay in the HTML; without JS they are shown stacked).
  root.classList.add("js");
  document.querySelectorAll(".views").forEach((box) => {
    const tabs = [...box.querySelectorAll(".view-tab")], views = [...box.querySelectorAll(".view")];
    const show = (i) => {
      tabs.forEach((t, k) => { t.classList.toggle("is-on", k === i); t.setAttribute("aria-pressed", k === i); });
      views.forEach((v, k) => v.classList.toggle("is-on", k === i));
    };
    tabs.forEach((t, k) => t.addEventListener("click", () => show(k)));
    show(0);
  });

  // News detail pages: thumbnails show their image in the large panel.
  const hero = document.getElementById("hero");
  const thumbs = [...document.querySelectorAll(".post-gallery .thumb")];
  thumbs.forEach((t) => t.addEventListener("click", (e) => {
    e.preventDefault();
    hero.src = t.getAttribute("href"); hero.width = +t.dataset.w; hero.height = +t.dataset.h;
    thumbs.forEach((x) => x.classList.toggle("is-on", x === t));
  }));

  // Highlight the section currently in view.
  const links = [...document.querySelectorAll(".nav a")];
  const byId = Object.fromEntries(links.map((a) => [a.hash.slice(1), a]));
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      links.forEach((a) => a.classList.toggle("active", a === byId[e.target.id]));
    }
  }, { rootMargin: "-35% 0px -60% 0px" });
  document.querySelectorAll("main section[id]").forEach((s) => io.observe(s));

  // Publication filters.
  const pubs = [...document.querySelectorAll(".pub")];
  const buttons = [...document.querySelectorAll(".filter")];
  buttons.forEach((b) => b.addEventListener("click", () => {
    const f = b.dataset.filter;
    buttons.forEach((x) => { x.classList.toggle("is-on", x === b); x.setAttribute("aria-pressed", x === b); });
    pubs.forEach((p) => {
      p.hidden = !(f === "all" || p.dataset.topic === f || (f === "first" && p.dataset.first === "true"));
    });
    document.querySelectorAll("h3.year").forEach((h) => {
      h.hidden = ![...h.nextElementSibling.children].some((p) => !p.hidden);
    });
  }));

  // Copy BibTeX.
  document.querySelectorAll(".copy").forEach((b) => b.addEventListener("click", async () => {
    const text = document.getElementById(b.dataset.copy).textContent;
    try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; }
    catch (e) { b.textContent = "Select and copy"; }
    setTimeout(() => { b.textContent = "Copy"; }, 1600);
  }));
})();
