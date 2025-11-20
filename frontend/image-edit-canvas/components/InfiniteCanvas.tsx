"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { GooeyLoader } from "./GooeyLoader";
import {
  submitQwenEdit,
  submitCameraAngle,
  pollJobStatus,
  submitFaceMask,
  submitFaceSwap,
  addImageToSession,
  updateImagePosition,
  deleteImage,
  type JobResponse,
} from "../lib/api";

type ImageItem = { key: string; url: string; x: number; y: number };
type Positioned = ImageItem;

// Processing job with placeholder
type ProcessingJob = {
  jobId: string;
  status: "pending" | "processing" | "completed" | "failed";
  type: "qwen" | "camera";
  sourceUrl: string;
  resultUrl?: string;
  x: number;
  y: number;
  transitionDuration?: number; // For ImageLoader transition speed
};

type Props = {
  images: ImageItem[];
  sessionId: string | null;
  onScaleChange?: (scale: number) => void;
  apiRef?: (api: {
    zoomIn: () => void;
    zoomOut: () => void;
    reset: () => void;
  }) => void;
};

const MIN_SCALE = 0.01;
const MAX_SCALE = 5;
const WHEEL_SENSITIVITY = 0.005;
const VIEWPORT_W = 12000; // Virtual viewport size at 100% zoom
const VIEWPORT_H = 8000;
// Scale factor: at 100% zoom, map screen pixels to virtual viewport pixels
// If 2000px image should be < 1/4 screen height (e.g., 270px on 1080p screen)
// then 2000 virtual px = ~270 screen px, so scale ≈ 0.135
// For 12000x8000 to fit nicely: on 1920x1080, scale = 1920/12000 ≈ 0.16 (width) or 1080/8000 ≈ 0.135 (height)
const BASE_SCALE = 0.12; // At 100% zoom, this scales the virtual world to screen

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}

export default function InfiniteCanvas({
  images,
  sessionId,
  onScaleChange,
  apiRef,
}: Props) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1.0); // Start at 100% scale
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const [panning, setPanning] = useState(false);
  const panStart = useRef<{ x: number; y: number } | null>(null);
  const centeredOnce = useRef(false);
  const [items, setItems] = useState<Positioned[]>([]);
  const dragInfo = useRef<{
    key: string;
    startX: number;
    startY: number;
    imgX: number;
    imgY: number;
  } | null>(null);
  const [selectedEl, setSelectedEl] = useState<HTMLImageElement | null>(null);
  const [overlay, setOverlay] = useState<{ cx: number; top: number } | null>(
    null
  );
  const [vpPanel, setVpPanel] = useState<{ left: number; top: number } | null>(
    null
  );
  const [showVpPanel, setShowVpPanel] = useState(false);
  const [vpRotation, setVpRotation] = useState<number>(0); // -90,-45,0,45,90
  const [vpVertical, setVpVertical] = useState<number>(0); // -2,-1,0,1,2
  const [vpMovement, setVpMovement] = useState<number>(0); // -1,0,1
  const [showEditPanel, setShowEditPanel] = useState(false);
  const [editPanel, setEditPanel] = useState<{
    left: number;
    top: number;
    width: number;
  } | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [sendingEdit, setSendingEdit] = useState(false);
  const [sendingCamera, setSendingCamera] = useState(false);
  const [processingJobs, setProcessingJobs] = useState<ProcessingJob[]>([]);
  // Face Swap states
  const [faceSwapPanel, setFaceSwapPanel] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const [showFaceSwapPanel, setShowFaceSwapPanel] = useState(false);
  const [faceSwapModel, setFaceSwapModel] = useState<string>("seedream");
  const [faceSwapTargetUrl, setFaceSwapTargetUrl] = useState<string>("");
  const [facePositionPrompt, setFacePositionPrompt] = useState<string>("");
  const [expressionPrompt, setExpressionPrompt] = useState<string>("");
  // Image metadata for displaying filename and dimensions
  const [imageMetadata, setImageMetadata] = useState<Record<string, { width: number; height: number; filename: string }>>({});
  const [sendingFaceSwap, setSendingFaceSwap] = useState(false);
  const editAreaRef = useRef<HTMLTextAreaElement | null>(null);
  const adjustEditHeight = useCallback(() => {
    const el = editAreaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const line = 20; // px line-height
    const max = line * 3 + 16; // up to 3 lines + padding
    const next = Math.min(el.scrollHeight, max);
    el.style.height = `${next}px`;
  }, []);
  const handleGenerate = useCallback(async () => {
    if (!selectedEl || sendingCamera) return;

    // Map rotation (-90, -45, 0, 45, 90) to horizontal parameter (-2, -1, 0, 1, 2)
    const rotationToHorizontal: Record<number, number> = {
      "-90": -2,
      "-45": -1,
      "0": 0,
      "45": 1,
      "90": 2,
    };
    const horizontal = rotationToHorizontal[vpRotation] ?? 0;

    try {
      setSendingCamera(true);

      // Get selected image position for placeholder
      const imgEl = selectedEl;
      const rect = imgEl.getBoundingClientRect();
      const actualScale = scale * BASE_SCALE;
      const placeholderX = (rect.right + 20 - tx) / actualScale;
      const placeholderY = (rect.top - ty) / actualScale;

      // Submit job
      const result = await submitCameraAngle(selectedEl.src, {
        vertical: vpVertical,
        horizontal: horizontal,
        zoom: vpMovement,
      });

      console.log("Camera angle job submitted:", result.job_id);

      // Add processing job to state
      const newJob: ProcessingJob = {
        jobId: result.job_id,
        status: "pending",
        type: "camera",
        sourceUrl: selectedEl.src,
        x: placeholderX,
        y: placeholderY,
        transitionDuration: 100000, // Long transition during processing
      };
      setProcessingJobs((prev) => [...prev, newJob]);

      // Start polling in background
      pollJobStatus(result.job_id, (status) => {
        setProcessingJobs((prev) =>
          prev.map((job) =>
            job.jobId === result.job_id
              ? {
                  ...job,
                  status: status.status,
                  resultUrl: status.result_url,
                  // Set short transition when completed for smooth final reveal
                  transitionDuration: status.status === "completed" ? 100 : job.transitionDuration,
                }
              : job
          )
        );

        // When job completes successfully, add to permanent items
        if (status.status === "completed" && status.result_url) {
          const resultUrl = status.result_url;

          // Extract S3 key from CloudFront URL
          const urlObj = new URL(resultUrl);
          const s3Key = urlObj.pathname.substring(1); // Remove leading slash

          // Add generated image to session so it persists across page refreshes
          if (sessionId) {
            addImageToSession(
              sessionId,
              s3Key,
              placeholderX,
              placeholderY
            ).catch((err) => {
              console.error("Failed to add image to session:", err);
            });
          }

          setItems((prev) => [
            ...prev,
            {
              key: s3Key, // Use S3 key instead of result-{jobId} for consistency
              url: resultUrl,
              x: placeholderX,
              y: placeholderY,
            },
          ]);

          // Remove from processing jobs after a short delay to allow fade transition
          setTimeout(() => {
            setProcessingJobs((prev) =>
              prev.filter((job) => job.jobId !== result.job_id)
            );
          }, 500);
        }
      }).catch((err) => {
        console.error("Polling failed:", err);
        setProcessingJobs((prev) =>
          prev.map((job) =>
            job.jobId === result.job_id ? { ...job, status: "failed" } : job
          )
        );
      });

      // Reset camera parameters
      setVpRotation(0);
      setVpVertical(0);
      setVpMovement(0);
      setShowVpPanel(false);
    } catch (err) {
      console.error("Camera angle submission failed:", err);
    } finally {
      setSendingCamera(false);
    }
  }, [
    selectedEl,
    vpRotation,
    vpVertical,
    vpMovement,
    sendingCamera,
    tx,
    ty,
    scale,
  ]);

  const downloadSelected = useCallback(async () => {
    if (!selectedEl) return;
    try {
      const res = await fetch(selectedEl.src, { mode: "cors" });
      const blob = await res.blob();
      const a = document.createElement("a");
      const url = URL.createObjectURL(blob);
      a.href = url;

      // Extract filename from URL, handling query parameters
      const urlObj = new URL(selectedEl.src);
      const pathname = urlObj.pathname;
      const filename = pathname.substring(pathname.lastIndexOf("/") + 1);

      // Use extracted filename or default to image.png
      a.download = filename || "image.png";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("download failed", e);
    }
  }, [selectedEl]);

  const deleteSelected = useCallback(async () => {
    if (!selectedEl || !sessionId) return;

    try {
      // Extract S3 key from CloudFront URL
      const urlObj = new URL(selectedEl.src);
      const s3Key = urlObj.pathname.substring(1); // Remove leading slash

      // Call backend delete API (canvas service)
      await deleteImage(sessionId, s3Key);

      // Remove from canvas items
      setItems((prev) => prev.filter((item) => item.url !== selectedEl.src));

      // Clear selection
      setSelectedEl(null);
      setShowVpPanel(false);
      setShowEditPanel(false);
    } catch (e) {
      console.error("delete failed", e);
      alert("Failed to delete image. Please try again.");
    }
  }, [selectedEl, sessionId]);

  const updateOverlay = useCallback(() => {
    if (!selectedEl) return;
    const r = selectedEl.getBoundingClientRect();
    setOverlay({ cx: r.left + r.width / 2, top: Math.max(8, r.top - 56) });
    setVpPanel({ left: r.right + 12, top: r.top + 12 });
    setFaceSwapPanel({ left: r.right + 12, top: r.top + 12 });
    const w = Math.min(Math.max(520, r.width), 760);
    setEditPanel({
      left: r.left + r.width / 2 - w / 2,
      top: r.bottom + 12,
      width: w,
    });
    setTimeout(adjustEditHeight, 0);
  }, [selectedEl, adjustEditHeight]);

  const onWheel = useCallback(
    (e: WheelEvent) => {
      // Check if the event target is inside a panel (edit panel, viewpoint panel, or face swap panel)
      const target = e.target as HTMLElement;
      const isInsidePanel = target.closest('[data-panel="true"]');

      // If scrolling inside a panel, don't zoom the canvas
      if (isInsidePanel) {
        return;
      }

      e.preventDefault();
      // Use viewport (window) coordinates directly so zoom anchors to cursor on screen
      const mx = e.clientX;
      const my = e.clientY;
      const currentActualScale = scale * BASE_SCALE;
      const wx = (mx - tx) / currentActualScale;
      const wy = (my - ty) / currentActualScale;
      const factor = Math.exp(-e.deltaY * WHEEL_SENSITIVITY);
      const newScale = clamp(scale * factor, MIN_SCALE, MAX_SCALE);
      const newActualScale = newScale * BASE_SCALE;
      setScale(newScale);
      setTx(mx - wx * newActualScale);
      setTy(my - wy * newActualScale);
    },
    [scale, tx, ty]
  );

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const vp = viewportRef.current;
    if (!vp) return;
    vp.setPointerCapture?.(e.pointerId);
    setPanning(true);
    panStart.current = { x: e.clientX, y: e.clientY };
    // Deselect any selected image when clicking on the canvas background
    setSelectedEl(null);
    setOverlay(null);
    setShowVpPanel(false);
    setShowFaceSwapPanel(false); // Issue #2 fix: close face swap panel when clicking away
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragInfo.current) {
        const di = dragInfo.current;
        const dx = (e.clientX - di.startX) / (scale * BASE_SCALE);
        const dy = (e.clientY - di.startY) / (scale * BASE_SCALE);
        setItems((prev) =>
          prev.map((it) =>
            it.key === di.key ? { ...it, x: di.imgX + dx, y: di.imgY + dy } : it
          )
        );
        // keep toolbar aligned while dragging
        updateOverlay();
        return;
      }
      if (!panning || !panStart.current) return;
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setTx((v) => v + dx);
      setTy((v) => v + dy);
      panStart.current = { x: e.clientX, y: e.clientY };
    },
    [panning, scale, updateOverlay]
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    const vp = viewportRef.current;
    vp?.releasePointerCapture?.(e.pointerId);
    setPanning(false);
    panStart.current = null;
    dragInfo.current = null;
  }, []);

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const w = (ev: Event) => onWheel(ev as WheelEvent);
    vp.addEventListener("wheel", w, { passive: false });
    return () => vp.removeEventListener("wheel", w);
  }, [onWheel]);

  useEffect(() => {
    if (centeredOnce.current) return;
    const vw = window.innerWidth || 0;
    const vh = window.innerHeight || 0;
    const actualScale = scale * BASE_SCALE;
    setTx((vw - VIEWPORT_W * actualScale) / 2);
    setTy((vh - VIEWPORT_H * actualScale) / 2);
    centeredOnce.current = true;
  }, [scale]);

  // Sync incoming images -> positioned list (preserve existing positions)
  useEffect(() => {
    setItems((prev) => {
      const existing = new Map(prev.map((p) => [p.key, p] as const));
      const next: Positioned[] = [];
      let offset = 0;
      for (const img of images) {
        const found = existing.get(img.key);
        if (found) {
          next.push(found);
        } else {
          // Use position from database if available, otherwise place with offset
          next.push(img);
          offset += 1;
        }
      }
      return next;
    });
  }, [images]);

  useEffect(() => {
    onScaleChange?.(scale);
  }, [scale, onScaleChange]);

  useEffect(() => {
    updateOverlay();
  }, [updateOverlay, scale, tx, ty]);

  useEffect(() => {
    // Adjust edit textarea height on content or visibility changes
    if (showEditPanel) {
      adjustEditHeight();
    }
  }, [editPrompt, showEditPanel, adjustEditHeight]);

  useEffect(() => {
    const onWin = () => updateOverlay();
    window.addEventListener("resize", onWin);
    return () => window.removeEventListener("resize", onWin);
  }, [updateOverlay]);

  useEffect(() => {
    if (!apiRef) return;
    const zoomBy = (f: number) => {
      const mx = (window.innerWidth || 0) / 2;
      const my = (window.innerHeight || 0) / 2;
      const wx = (mx - tx) / scale;
      const wy = (my - ty) / scale;
      const ns = clamp(scale * f, MIN_SCALE, MAX_SCALE);
      setScale(ns);
      setTx(mx - wx * ns);
      setTy(my - wy * ns);
    };
    const zoomIn = () => zoomBy(1.35);
    const zoomOut = () => zoomBy(1 / 1.35);
    const reset = () => {
      setScale(1);
      const vw = window.innerWidth || 0;
      const vh = window.innerHeight || 0;
      setTx((vw - VIEWPORT_W) / 2);
      setTy((vh - VIEWPORT_H) / 2);
    };
    apiRef({ zoomIn, zoomOut, reset });
  }, [apiRef, scale, tx, ty]);

  const actualScale = scale * BASE_SCALE;

  return (
    <>
      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}</style>
      <div
        ref={viewportRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{
          position: "fixed",
          left: 0,
          top: 0,
          width: "100%",
          height: "100%",
          overflow: "hidden",
          cursor: panning ? "grabbing" : "grab",
          background:
            "repeating-conic-gradient(#f8f8f8 0% 25%, #ffffff 0% 50%) 50% / 40px 40px",
          backgroundSize: `${40 * actualScale}px ${40 * actualScale}px`,
          backgroundPosition: `${tx}px ${ty}px`,
        }}
      >
      {items.map((img) => {
        const left = tx + img.x * actualScale;
        const top = ty + img.y * actualScale;
        const metadata = imageMetadata[img.key];
        const filename = img.key.split('/').pop() || img.key;

        return (
          <React.Fragment key={img.key}>
            {/* Image label */}
            {metadata && (
              <div
                style={{
                  position: "fixed",
                  left,
                  top: top - 24 * actualScale,
                  transform: `scale(${actualScale})`,
                  transformOrigin: "0 0",
                  background: "rgba(0, 0, 0, 0.75)",
                  color: "white",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontFamily: "monospace",
                  whiteSpace: "nowrap",
                  pointerEvents: "none",
                  userSelect: "none",
                }}
              >
                {filename} • {metadata.width}×{metadata.height}
              </div>
            )}
            <img
              src={img.url}
              style={{
                position: "fixed",
                left,
                top,
                transform: `scale(${actualScale})`,
                transformOrigin: "0 0",
                userSelect: "none",
                pointerEvents: "auto",
                cursor: "move",
                width: "auto",
                height: "auto",
              }}
              alt={img.key}
              draggable={false}
              onLoad={(e) => {
                const imgEl = e.currentTarget;
                setImageMetadata((prev) => ({
                  ...prev,
                  [img.key]: {
                    width: imgEl.naturalWidth,
                    height: imgEl.naturalHeight,
                    filename,
                  },
                }));
              }}
              onPointerDown={(e) => {
                e.stopPropagation();
                (e.currentTarget as any).setPointerCapture?.(e.pointerId);
                setSelectedEl(e.currentTarget);
                setShowFaceSwapPanel(false); // Issue #2 fix: close face swap panel when selecting different image
                updateOverlay();
                dragInfo.current = {
                  key: img.key,
                  startX: e.clientX,
                  startY: e.clientY,
                  imgX: img.x,
                  imgY: img.y,
                };
              }}
            onPointerUp={(e) => {
              (e.currentTarget as any).releasePointerCapture?.(e.pointerId);

              // Save position to database after drag
              if (dragInfo.current && sessionId) {
                const updatedItem = items.find(
                  (item) => item.key === dragInfo.current!.key
                );
                if (
                  updatedItem &&
                  typeof updatedItem.x === "number" &&
                  typeof updatedItem.y === "number"
                ) {
                  updateImagePosition(
                    sessionId,
                    updatedItem.key,
                    updatedItem.x,
                    updatedItem.y
                  ).catch((err) => {
                    console.error("Failed to save position:", err);
                  });
                }
              }

              dragInfo.current = null;
            }}
            onClick={(e) => {
              e.stopPropagation();
              setSelectedEl(e.currentTarget);
              setShowFaceSwapPanel(false); // Issue #2 fix: close face swap panel when selecting different image
              updateOverlay();
            }}
          />
          </React.Fragment>
        );
      })}
      {/* Render processing job placeholders */}
      {processingJobs.map((job) => {
        const left = tx + job.x * actualScale;
        const top = ty + job.y * actualScale;

        // If job completed, show the result image
        if (job.status === "completed" && job.resultUrl) {
          return (
            <img
              key={`job-${job.jobId}`}
              src={job.resultUrl}
              style={{
                position: "fixed",
                left,
                top,
                transform: `scale(${actualScale})`,
                transformOrigin: "0 0",
                userSelect: "none",
                pointerEvents: "auto",
                cursor: "move",
                width: "auto",
                height: "auto",
              }}
              alt={`result-${job.jobId}`}
              draggable={false}
              onPointerDown={(e) => {
                e.stopPropagation();
                const target = e.currentTarget as HTMLImageElement;
                setSelectedEl(target);
                setShowFaceSwapPanel(false); // Issue #2 fix: close face swap panel when selecting different image
                updateOverlay();
                setShowVpPanel(false);
                setShowEditPanel(false);
              }}
            />
          );
        }

        // Show GooeyLoader for pending/processing jobs
        if ((job.status === "pending" || job.status === "processing") && job.sourceUrl) {
          return (
            <div
              key={`job-${job.jobId}`}
              style={{
                position: "fixed",
                left,
                top,
                transform: `scale(${actualScale})`,
                transformOrigin: "0 0",
                width: 512,
                height: 512,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                pointerEvents: "none",
              }}
            >
              <GooeyLoader
                primaryColor="#60a5fa"
                secondaryColor="#3b82f6"
                borderColor="#e5e7eb"
              />
            </div>
          );
        }

        // Show result image when completed
        if (job.status === "completed" && job.resultUrl) {
          return (
            <img
              key={`job-${job.jobId}`}
              src={job.resultUrl}
              style={{
                position: "fixed",
                left,
                top,
                transform: `scale(${actualScale})`,
                transformOrigin: "0 0",
                width: "auto",
                height: "auto",
                animation: "fadeIn 0.3s ease-in",
                pointerEvents: "none",
              }}
              alt="Result"
            />
          );
        }

        // Show placeholder for failed jobs
        return (
          <div
            key={`job-${job.jobId}`}
            style={{
              position: "fixed",
              left,
              top,
              transform: `scale(${actualScale})`,
              transformOrigin: "0 0",
              width: 512,
              height: 512,
              background: "linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%)",
              border: "2px dashed #f44336",
              borderRadius: 8,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                fontSize: 14,
                color: "#666",
                textAlign: "center",
                padding: "0 20px",
              }}
            >
              ❌ Processing Failed
            </div>
            {job.status === "pending" && job.jobId && (
              <div style={{ fontSize: 11, color: "#999" }}>
                Job ID: {job.jobId.slice(0, 8)}...
              </div>
            )}
          </div>
        );
      })}
      {selectedEl && overlay && (
        <div
          style={{
            position: "fixed",
            left: overlay.cx,
            top: overlay.top,
            transform: "translateX(-50%)",
            background: "#fff",
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
            padding: "6px 10px",
            display: "flex",
            gap: 8,
            zIndex: 1000,
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <button
            style={{
              border: "none",
              background: "transparent",
              padding: "6px 10px",
              borderRadius: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
            onClick={(e) => {
              e.stopPropagation();
              setShowEditPanel((v) => !v);
              setShowVpPanel(false);
              setShowFaceSwapPanel(false);
              updateOverlay();
            }}
          >
            <img src="/icons/qwen.png" alt="Qwen" width={16} height={16} />
            Qwen Edit
          </button>
          <div style={{ width: 1, background: "#eee" }} />
          <button
            style={{
              border: "none",
              background: "transparent",
              padding: "6px 10px",
              borderRadius: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
            onClick={(e) => {
              e.stopPropagation();
              setShowVpPanel((v) => !v);
              setShowEditPanel(false);
              setShowFaceSwapPanel(false);
              updateOverlay();
            }}
          >
            <img src="/icons/flip.png" alt="View" width={16} height={16} />
            Change Viewpoint
          </button>
          <div style={{ width: 1, background: "#eee" }} />
          <button
            title="Face Swap"
            style={{
              border: "none",
              background: "transparent",
              padding: "6px 10px",
              borderRadius: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
            onClick={(e) => {
              e.stopPropagation();
              setShowFaceSwapPanel((v) => !v);
              setShowVpPanel(false); // Close viewpoint panel
              setShowEditPanel(false); // Close edit panel
              updateOverlay();
            }}
          >
            <img src="/icons/swap.png" alt="Swap" width={16} height={16} />
            Face Swap
          </button>
          <div style={{ width: 1, background: "#eee" }} />
          <button
            title="Download"
            onClick={(e) => {
              e.stopPropagation();
              downloadSelected();
            }}
            style={{
              border: "none",
              background: "transparent",
              padding: "6px 10px",
              borderRadius: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <img
              src="/icons/download.png"
              alt="Download"
              width={16}
              height={16}
            />
          </button>
          <div style={{ width: 1, background: "#eee" }} />
          <button
            title="Delete"
            onClick={(e) => {
              e.stopPropagation();
              deleteSelected();
            }}
            style={{
              border: "none",
              background: "transparent",
              padding: "6px 10px",
              borderRadius: 8,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <img src="/icons/trash.png" alt="Delete" width={16} height={16} />
          </button>
        </div>
      )}
      {selectedEl && showVpPanel && vpPanel && (
        <div
          data-panel="true"
          style={{
            position: "fixed",
            left: vpPanel.left,
            top: vpPanel.top,
            background: "#fff",
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
            padding: 12,
            zIndex: 1001,
            minWidth: 220,
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
            Camera Rotation
          </div>
          <div
            style={{ display: "flex", alignItems: "center", marginBottom: 10 }}
          >
            <span style={{ minWidth: 40, color: "#999" }}>Left</span>
            <div
              style={{
                display: "flex",
                gap: 6,
                flex: 1,
                justifyContent: "center",
              }}
            >
              {[-90, -45, 0, 45, 90].map((v) => (
                <button
                  key={v}
                  onClick={() => setVpRotation(v)}
                  style={{
                    padding: "6px 8px",
                    borderRadius: 8,
                    border:
                      v === vpRotation ? "2px solid #111" : "1px solid #ddd",
                    background: v === vpRotation ? "#f4f4f4" : "#fff",
                    cursor: "pointer",
                  }}
                >
                  {v}
                </button>
              ))}
            </div>
            <span style={{ minWidth: 48, textAlign: "right", color: "#999" }}>
              Right
            </span>
          </div>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
            Vertical Angle
          </div>
          <div
            style={{ display: "flex", alignItems: "center", marginBottom: 10 }}
          >
            <span style={{ minWidth: 48, color: "#999" }}>Lower</span>
            <div
              style={{
                display: "flex",
                gap: 6,
                flex: 1,
                justifyContent: "center",
              }}
            >
              {[-2, -1, 0, 1, 2].map((v) => (
                <button
                  key={v}
                  onClick={() => setVpVertical(v)}
                  style={{
                    padding: "6px 8px",
                    borderRadius: 8,
                    border:
                      v === vpVertical ? "2px solid #111" : "1px solid #ddd",
                    background: v === vpVertical ? "#f4f4f4" : "#fff",
                    cursor: "pointer",
                  }}
                >
                  {v}
                </button>
              ))}
            </div>
            <span style={{ minWidth: 52, textAlign: "right", color: "#999" }}>
              Higher
            </span>
          </div>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
            Movement
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[-1, 0, 1].map((v) => (
              <button
                key={v}
                onClick={() => setVpMovement(v)}
                style={{
                  padding: "6px 8px",
                  borderRadius: 8,
                  border:
                    v === vpMovement ? "2px solid #111" : "1px solid #ddd",
                  background: v === vpMovement ? "#f4f4f4" : "#fff",
                  cursor: "pointer",
                }}
              >
                {v === -1 ? "Back" : v === 0 ? "0" : "Forward"}
              </button>
            ))}
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginTop: 12,
            }}
          >
            <button
              onClick={handleGenerate}
              disabled={sendingCamera}
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                border: "none",
                color: "#fff",
                background: sendingCamera ? "#999" : "#111",
                cursor: sendingCamera ? "default" : "pointer",
              }}
            >
              {sendingCamera ? "Sending..." : "Generate"}
            </button>
          </div>
        </div>
      )}
      {selectedEl && showEditPanel && editPanel && (
        <div
          data-panel="true"
          style={{
            position: "fixed",
            left: editPanel.left,
            top: editPanel.top,
            width: editPanel.width,
            background: "#fff",
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
            padding: 10,
            zIndex: 1001,
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!editPrompt?.trim() || !selectedEl || sendingEdit) return;

              try {
                setSendingEdit(true);

                // Get selected image position for placeholder
                const imgEl = selectedEl;
                const rect = imgEl.getBoundingClientRect();
                const actualScale = scale * BASE_SCALE;
                const placeholderX = (rect.right + 20 - tx) / actualScale;
                const placeholderY = (rect.top - ty) / actualScale;

                // Submit job
                const result = await submitQwenEdit(
                  selectedEl.src,
                  editPrompt.trim()
                );
                console.log("Qwen edit job submitted:", result.job_id);

                // Add processing job to state
                const newJob: ProcessingJob = {
                  jobId: result.job_id,
                  status: "pending",
                  type: "qwen",
                  sourceUrl: selectedEl.src,
                  x: placeholderX,
                  y: placeholderY,
                  transitionDuration: 100000, // Long transition during processing
                };
                setProcessingJobs((prev) => [...prev, newJob]);

                // Start polling in background
                pollJobStatus(result.job_id, (status) => {
                  setProcessingJobs((prev) =>
                    prev.map((job) =>
                      job.jobId === result.job_id
                        ? {
                            ...job,
                            status: status.status,
                            resultUrl: status.result_url,
                            // Set short transition when completed for smooth final reveal
                            transitionDuration: status.status === "completed" ? 100 : job.transitionDuration,
                          }
                        : job
                    )
                  );

                  // When job completes successfully, add to permanent items
                  if (status.status === "completed" && status.result_url) {
                    const resultUrl = status.result_url;

                    // Extract S3 key from CloudFront URL
                    const urlObj = new URL(resultUrl);
                    const s3Key = urlObj.pathname.substring(1); // Remove leading slash

                    // Add generated image to session so it persists across page refreshes
                    if (sessionId) {
                      addImageToSession(
                        sessionId,
                        s3Key,
                        placeholderX,
                        placeholderY
                      ).catch((err) => {
                        console.error("Failed to add image to session:", err);
                      });
                    }

                    setItems((prev) => [
                      ...prev,
                      {
                        key: s3Key, // Use S3 key instead of result-{jobId} for consistency
                        url: resultUrl,
                        x: placeholderX,
                        y: placeholderY,
                      },
                    ]);

                    // Remove from processing jobs after a short delay
                    setTimeout(() => {
                      setProcessingJobs((prev) =>
                        prev.filter((job) => job.jobId !== result.job_id)
                      );
                    }, 500);
                  }
                }).catch((err) => {
                  console.error("Polling failed:", err);
                  setProcessingJobs((prev) =>
                    prev.map((job) =>
                      job.jobId === result.job_id
                        ? { ...job, status: "failed" }
                        : job
                    )
                  );
                });

                // Clear input and close panel
                setEditPrompt("");
                setShowEditPanel(false);
              } catch (err) {
                console.error("Qwen edit submission failed:", err);
              } finally {
                setSendingEdit(false);
              }
            }}
            style={{ display: "flex", gap: 8 }}
          >
            <textarea
              ref={editAreaRef}
              value={editPrompt}
              rows={1}
              onChange={(e) => {
                setEditPrompt(e.target.value);
                adjustEditHeight();
              }}
              placeholder="Describe your edit..."
              style={{
                flex: 1,
                padding: "5px",
                border: "1px solid #ddd",
                borderRadius: 8,
                resize: "none",
                minHeight: 16,
                lineHeight: "20px",
                fontSize: 14,
                overflow: "hidden",
              }}
            />
            <button
              type="submit"
              disabled={sendingEdit}
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                border: "none",
                background: sendingEdit ? "#999" : "#111",
                color: "#fff",
                cursor: sendingEdit ? "default" : "pointer",
              }}
            >
              {sendingEdit ? "Sending..." : "Send"}
            </button>
          </form>
        </div>
      )}
      {/* Face Swap Panel */}
      {selectedEl && showFaceSwapPanel && faceSwapPanel && (
        <div
          data-panel="true"
          style={{
            position: "fixed",
            left: faceSwapPanel.left,
            top: faceSwapPanel.top,
            background: "#fff",
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
            padding: 12,
            zIndex: 1001,
            width: 360,
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          {/* Model Selection */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
              Model
            </div>
            <select
              value={faceSwapModel}
              onChange={(e) => setFaceSwapModel(e.target.value)}
              style={{
                width: "100%",
                padding: "6px 8px",
                border: "1px solid #ddd",
                borderRadius: 6,
                fontSize: 13,
                background: "#fff",
                cursor: "pointer",
              }}
            >
              <option value="seedream">Seedream</option>
              <option value="nano-banana" disabled>
                Nano Banana (Coming Soon)
              </option>
            </select>
          </div>

          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
            Face Reference Image
          </div>

          {/* Image Grid - 2 rows x 4 columns with scroll */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 6,
              marginBottom: 12,
              maxHeight: 160,
              overflowY: "auto",
            }}
            onWheel={(e) => {
              // Let the div scroll naturally, but prevent propagation to canvas
              e.stopPropagation();
              // Stop the native event from reaching the viewport listener
              if (e.nativeEvent.stopImmediatePropagation) {
                e.nativeEvent.stopImmediatePropagation();
              }
            }}
          >
            {items
              .filter((item) => item.url !== selectedEl.src)
              .map((item) => (
                <div
                  key={item.key}
                  onClick={() => setFaceSwapTargetUrl(item.url)}
                  style={{
                    position: "relative",
                    aspectRatio: "1",
                    borderRadius: 6,
                    overflow: "hidden",
                    cursor: "pointer",
                    border:
                      faceSwapTargetUrl === item.url
                        ? "2px solid #111"
                        : "1px solid #ddd",
                    background: "#f8f8f8",
                  }}
                >
                  <img
                    src={item.url}
                    alt=""
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                    }}
                  />
                </div>
              ))}
          </div>

          {/* Face Position Prompt */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
              Face Position Prompt (Optional)
            </div>
            <input
              type="text"
              value={facePositionPrompt}
              onChange={(e) => setFacePositionPrompt(e.target.value)}
              placeholder="e.g., person on the left, woman in red"
              style={{
                width: "100%",
                padding: "6px 8px",
                border: "1px solid #ddd",
                borderRadius: 6,
                fontSize: 13,
                boxSizing: "border-box",
              }}
            />
          </div>

          {/* Expression Prompt */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
              Expression Prompt (Optional)
            </div>
            <input
              type="text"
              value={expressionPrompt}
              onChange={(e) => setExpressionPrompt(e.target.value)}
              placeholder="e.g., smiling, serious, surprised"
              style={{
                width: "100%",
                padding: "6px 8px",
                border: "1px solid #ddd",
                borderRadius: 6,
                fontSize: 13,
                boxSizing: "border-box",
              }}
            />
          </div>

          {/* Generate Button */}
          <button
            onClick={async () => {
              if (!selectedEl || !faceSwapTargetUrl || sendingFaceSwap) return;

              try {
                setSendingFaceSwap(true);

                // Get selected image position for result placement
                const imgEl = selectedEl;
                const rect = imgEl.getBoundingClientRect();
                const actualScale = scale * BASE_SCALE;
                const resultX = (rect.right + 20 - tx) / actualScale;
                const resultY = (rect.top - ty) / actualScale;

                // Step 1: Submit face mask task
                console.log("Step 1: Submitting face mask task...");
                const maskResult = await submitFaceMask(selectedEl.src, {
                  facePositionPrompt: facePositionPrompt || undefined,
                });

                console.log("Face mask task submitted:", maskResult.job_id);

                // Step 2: Poll face mask task until completion
                console.log("Step 2: Waiting for face mask to complete...");
                const maskCompleted = await pollJobStatus(maskResult.job_id);

                if (maskCompleted.status !== "completed" || !maskCompleted.result_url) {
                  throw new Error("Face mask failed: " + (maskCompleted.error || "Unknown error"));
                }

                console.log("Face mask completed:", maskCompleted.result_url);

                // Step 3: Display masked image on canvas
                const maskedImageUrl = maskCompleted.result_url;
                const maskedUrlObj = new URL(maskedImageUrl);
                const maskedS3Key = maskedUrlObj.pathname.substring(1);

                setItems((prev) => [
                  ...prev,
                  {
                    key: maskedS3Key,
                    url: maskedImageUrl,
                    x: resultX,
                    y: resultY,
                  },
                ]);

                // Add masked image to session
                if (sessionId) {
                  await addImageToSession(sessionId, maskedS3Key, resultX, resultY).catch((err) => {
                    console.error("Failed to add masked image to session:", err);
                  });
                }

                // Step 4: Submit face swap task using masked image
                // Note: maskedImageUrl is already masked, API will not detect/mask again
                console.log("Step 4: Submitting face swap task...");
                const swapResult = await submitFaceSwap(maskedImageUrl, faceSwapTargetUrl, {
                  model: faceSwapModel,
                  expressionPrompt: expressionPrompt || undefined,
                });

                console.log("Face swap task submitted:", swapResult.job_id);

                // Close panel immediately after successful submission (Issue #1 fix)
                setShowFaceSwapPanel(false);
                setFaceSwapTargetUrl("");
                setFacePositionPrompt("");
                setExpressionPrompt("");

                // Add face swap job to processing state (will show loading on masked image)
                const swapJob: ProcessingJob = {
                  jobId: swapResult.job_id,
                  status: "pending",
                  type: "camera",
                  sourceUrl: maskedImageUrl,
                  x: resultX,
                  y: resultY,
                  transitionDuration: 100000, // Long transition during processing
                };
                setProcessingJobs((prev) => [...prev, swapJob]);

                // Step 5: Poll face swap task
                pollJobStatus(swapResult.job_id, (status) => {
                  setProcessingJobs((prev) =>
                    prev.map((job) =>
                      job.jobId === swapResult.job_id
                        ? {
                            ...job,
                            status: status.status,
                            resultUrl: status.result_url,
                            // Set short transition when completed for smooth final reveal
                            transitionDuration: status.status === "completed" ? 100 : job.transitionDuration,
                          }
                        : job
                    )
                  );

                  // When face swap completes successfully
                  if (status.status === "completed" && status.result_url) {
                    const finalUrl = status.result_url;
                    const finalUrlObj = new URL(finalUrl);
                    const finalS3Key = finalUrlObj.pathname.substring(1);

                    // Remove masked image from items
                    setItems((prev) => prev.filter((item) => item.key !== maskedS3Key));

                    // Add final swapped image to items
                    setItems((prev) => [
                      ...prev,
                      {
                        key: finalS3Key,
                        url: finalUrl,
                        x: resultX,
                        y: resultY,
                      },
                    ]);

                    // Add final image to session
                    if (sessionId) {
                      addImageToSession(sessionId, finalS3Key, resultX, resultY).catch((err) => {
                        console.error("Failed to add final image to session:", err);
                      });
                    }

                    // Remove processing job
                    setTimeout(() => {
                      setProcessingJobs((prev) =>
                        prev.filter((job) => job.jobId !== swapResult.job_id)
                      );
                    }, 500);
                  }
                }).catch((err) => {
                  console.error("Face swap polling failed:", err);
                  setProcessingJobs((prev) =>
                    prev.map((job) =>
                      job.jobId === swapResult.job_id ? { ...job, status: "failed" } : job
                    )
                  );
                });

                // Panel already closed earlier (after submission)
              } catch (err) {
                console.error("Face swap workflow error:", err);
                alert("Face swap failed: " + (err instanceof Error ? err.message : String(err)));
              } finally {
                setSendingFaceSwap(false);
              }
            }}
            disabled={!faceSwapTargetUrl || sendingFaceSwap}
            style={{
              width: "100%",
              padding: "8px 12px",
              borderRadius: 8,
              border: "none",
              color: "#fff",
              background: sendingFaceSwap
                ? "#999"
                : !faceSwapTargetUrl
                ? "#ccc"
                : "#111",
              cursor:
                sendingFaceSwap || !faceSwapTargetUrl ? "default" : "pointer",
            }}
          >
            {sendingFaceSwap ? "Sending..." : "Generate"}
          </button>
        </div>
      )}
      </div>
    </>
  );
}
