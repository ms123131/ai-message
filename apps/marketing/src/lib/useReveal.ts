import { useEffect, useRef } from "react";

// Появление элемента при попадании в зону видимости. Один общий observer
// на все элементы — дешевле, чем по observer на узел. Выставляет
// data-visible="true", дальше всё делает CSS (.reveal в index.css).
//
// SITE_PLAN: «скупо — fade-in для секций при скролле через
// IntersectionObserver, без библиотек».
export function useReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Если IntersectionObserver недоступен — показываем сразу.
    if (typeof IntersectionObserver === "undefined") {
      el.dataset.visible = "true";
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.visible = "true";
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -10% 0px" },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return ref;
}
