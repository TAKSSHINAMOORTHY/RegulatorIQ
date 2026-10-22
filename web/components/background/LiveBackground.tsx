"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { BgTier, determineTier, detectEnvironmentCapabilities } from "./policy";
import { useMotionPreference } from "@/lib/motion";

export function LiveBackground() {
  const { resolvedTheme } = useTheme();
  const { prefersReducedMotion } = useMotionPreference();
  const [tier, setTier] = useState<BgTier>("static");
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Background performance state exposed for E2E and telemetry
  const stateRef = useRef({
    tier: "static" as BgTier,
    fps: 60,
    frameCount: 0,
    paused: false,
    scale: 1.0,
  });

  useEffect(() => {
    const caps = detectEnvironmentCapabilities();
    if (prefersReducedMotion) {
      caps.prefersReducedMotion = true;
    }
    const selected = determineTier(caps);
    setTier(selected);
    stateRef.current.tier = selected;

    if (typeof window !== "undefined") {
      (window as any).__bg = stateRef.current;
    }
  }, [prefersReducedMotion]);

  useEffect(() => {
    if (tier === "static" || !canvasRef.current) {
      return;
    }

    const canvas = canvasRef.current;
    let animId = 0;
    let lastTime = performance.now();
    let frameTimes: number[] = [];
    let scale = 1.0;
    let blurTimeout: any = null;
    let isDark = resolvedTheme === "dark";

    // 1. WebGL Initialization if tier is webgl
    let gl: WebGLRenderingContext | WebGL2RenderingContext | null = null;
    let program: WebGLProgram | null = null;
    let positionLocation = -1;
    let timeLocation: WebGLUniformLocation | null = null;
    let resolutionLocation: WebGLUniformLocation | null = null;
    let themeLocation: WebGLUniformLocation | null = null;

    if (tier === "webgl") {
      gl = canvas.getContext("webgl2") || (canvas.getContext("webgl") as any);
      if (!gl) {
        setTier("canvas");
        stateRef.current.tier = "canvas";
        return;
      }

      const vsSource = `
        attribute vec2 position;
        void main() {
          gl_Position = vec4(position, 0.0, 1.0);
        }
      `;

      const fsSource = `
        precision mediump float;
        uniform vec2 u_resolution;
        uniform float u_time;
        uniform float u_dark;

        void main() {
          vec2 st = gl_FragCoord.xy / u_resolution.xy;
          float t = u_time * 0.15;

          // Flowing sinusoidal ledger lines
          float wave1 = sin(st.x * 6.0 + t + sin(st.y * 3.0 + t * 0.8)) * 0.5 + 0.5;
          float wave2 = cos(st.y * 8.0 - t * 0.7 + cos(st.x * 4.0 - t)) * 0.5 + 0.5;
          float flow = mix(wave1, wave2, 0.5);

          // Lines motif
          float line = abs(sin((st.y + flow * 0.06) * 45.0));
          line = smoothstep(0.92, 0.98, line);

          // Theme palettes
          vec3 paperBg = vec3(0.98, 0.96, 0.93);
          vec3 saffronGlow = vec3(0.76, 0.38, 0.0);
          vec3 inkLine = vec3(0.11, 0.10, 0.09);

          vec3 midnightBg = vec3(0.04, 0.06, 0.12);
          vec3 auroraTeal = vec3(0.18, 0.83, 0.75);
          vec3 auroraViolet = vec3(0.49, 0.36, 1.0);

          vec3 lightColor = mix(paperBg, saffronGlow, flow * 0.18) + inkLine * line * 0.08;
          vec3 darkAurora = mix(auroraTeal, auroraViolet, flow);
          vec3 darkColor = midnightBg + darkAurora * (line * 0.25 + flow * 0.12);

          vec3 finalColor = mix(lightColor, darkColor, u_dark);
          gl_FragColor = vec4(finalColor, 1.0);
        }
      `;

      const createShader = (type: number, src: string) => {
        const shader = gl!.createShader(type);
        if (!shader) return null;
        gl!.shaderSource(shader, src);
        gl!.compileShader(shader);
        return shader;
      };

      const vs = createShader(gl.VERTEX_SHADER, vsSource);
      const fs = createShader(gl.FRAGMENT_SHADER, fsSource);
      if (vs && fs) {
        program = gl.createProgram();
        if (program) {
          gl.attachShader(program, vs);
          gl.attachShader(program, fs);
          gl.linkProgram(program);
          gl.useProgram(program);

          const buffer = gl.createBuffer();
          gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
          // Full-screen triangle
          gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array([-1.0, -1.0, 3.0, -1.0, -1.0, 3.0]),
            gl.STATIC_DRAW
          );

          positionLocation = gl.getAttribLocation(program, "position");
          timeLocation = gl.getUniformLocation(program, "u_time");
          resolutionLocation = gl.getUniformLocation(program, "u_resolution");
          themeLocation = gl.getUniformLocation(program, "u_dark");

          gl.enableVertexAttribArray(positionLocation);
          gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
        }
      }
    }

    // 2. Canvas2D Fallback state
    const ctx = tier === "canvas" ? canvas.getContext("2d") : null;
    interface Drifter {
      x: number;
      y: number;
      vx: number;
      length: number;
      alpha: number;
    }
    const drifters: Drifter[] = [];
    if (tier === "canvas" && ctx) {
      for (let i = 0; i < 60; i++) {
        drifters.push({
          x: Math.random() * window.innerWidth,
          y: Math.random() * window.innerHeight,
          vx: 0.2 + Math.random() * 0.4,
          length: 40 + Math.random() * 120,
          alpha: 0.1 + Math.random() * 0.3,
        });
      }
    }

    // 3. Render Loop with Frame-Rate Governor
    const updateSize = () => {
      const dpr = Math.min(1.5, window.devicePixelRatio || 1);
      const w = Math.floor(window.innerWidth * dpr * scale);
      const h = Math.floor(window.innerHeight * dpr * scale);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    };
    updateSize();

    let consecutiveFastFrames = 0;

    const render = (now: number) => {
      if (stateRef.current.paused) {
        return;
      }

      const delta = now - lastTime;
      lastTime = now;
      frameTimes.push(delta);
      if (frameTimes.length > 60) frameTimes.shift();

      // Governor metrics
      const avgFrameTime = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length;
      stateRef.current.fps = Math.round(1000 / (avgFrameTime || 16.6));
      stateRef.current.frameCount++;

      // Downscaling if frame time exceeds budget (> 24ms = < 40fps)
      if (frameTimes.length >= 60 && avgFrameTime > 24) {
        if (scale > 0.5) {
          scale = scale === 1.0 ? 0.75 : 0.5;
          stateRef.current.scale = scale;
          updateSize();
          frameTimes = [];
        } else {
          // Downgrade tier
          const nextTier: BgTier = tier === "webgl" ? "canvas" : "static";
          try {
            sessionStorage.setItem("regulatoriq_bg_tier", nextTier);
          } catch {}
          setTier(nextTier);
          stateRef.current.tier = nextTier;
          return;
        }
      } else if (frameTimes.length >= 60 && avgFrameTime < 12 && scale < 1.0) {
        consecutiveFastFrames++;
        if (consecutiveFastFrames > 300) {
          scale = Math.min(1.0, scale + 0.25);
          stateRef.current.scale = scale;
          updateSize();
          consecutiveFastFrames = 0;
          frameTimes = [];
        }
      }

      isDark = resolvedTheme === "dark";

      if (tier === "webgl" && gl && program) {
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform1f(timeLocation, now * 0.001);
        gl.uniform2f(resolutionLocation, canvas.width, canvas.height);
        gl.uniform1f(themeLocation, isDark ? 1.0 : 0.0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      } else if (tier === "canvas" && ctx) {
        ctx.fillStyle = isDark ? "#0A0F1E" : "#FAF6EE";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.lineWidth = 1;
        for (const d of drifters) {
          d.x += d.vx;
          if (d.x > canvas.width + 100) d.x = -100;
          ctx.strokeStyle = isDark
            ? `rgba(45, 212, 191, ${d.alpha * 0.5})`
            : `rgba(194, 97, 0, ${d.alpha * 0.35})`;
          ctx.beginPath();
          ctx.moveTo(d.x, d.y);
          ctx.lineTo(d.x + d.length, d.y);
          ctx.stroke();
        }
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    // Lifecycle handlers: pause when hidden or blurred > 10s
    const handleVisibility = () => {
      const isHidden = document.hidden;
      stateRef.current.paused = isHidden;
      if (!isHidden) {
        lastTime = performance.now();
        animId = requestAnimationFrame(render);
      }
    };

    const handleBlur = () => {
      blurTimeout = setTimeout(() => {
        stateRef.current.paused = true;
      }, 10000);
    };

    const handleFocus = () => {
      if (blurTimeout) clearTimeout(blurTimeout);
      if (stateRef.current.paused && !document.hidden) {
        stateRef.current.paused = false;
        lastTime = performance.now();
        animId = requestAnimationFrame(render);
      }
    };

    const handleResize = () => {
      updateSize();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("blur", handleBlur);
    window.addEventListener("focus", handleFocus);
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animId);
      if (blurTimeout) clearTimeout(blurTimeout);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("resize", handleResize);
    };
  }, [tier, resolvedTheme]);

  return (
    <div
      ref={containerRef}
      data-bg-tier={tier}
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none -z-10 overflow-hidden"
    >
      {tier === "static" ? (
        <div className="absolute inset-0 bg-bg transition-colors duration-500 ledger-ruled opacity-80">
          <div className="absolute inset-0 bg-gradient-to-tr from-accent/5 via-transparent to-accent-2/5" />
        </div>
      ) : (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full object-cover transition-opacity duration-700"
        />
      )}
      {/* Veil layer ensuring high text contrast */}
      <div className="absolute inset-0 bg-bg/85 backdrop-blur-[2px] pointer-events-none" />
    </div>
  );
}
