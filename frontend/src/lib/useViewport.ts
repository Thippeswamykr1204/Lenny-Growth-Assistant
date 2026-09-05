"use client";

import { useEffect, useState } from "react";

export type ViewportClass = "desktop" | "tablet" | "mobile";

function classify(width: number): ViewportClass {
  if (width >= 1024) return "desktop";
  if (width >= 768) return "tablet";
  return "mobile";
}

export function useViewportClass(): ViewportClass {
  const [viewport, setViewport] = useState<ViewportClass>("desktop");

  useEffect(() => {
    function update() {
      setViewport(classify(window.innerWidth));
    }
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return viewport;
}