"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cx } from "../../lib/cx";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Drawer({ open, onClose, title, children, footer, width = 560 }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="ax-drawer-overlay" role="presentation" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        className="ax-drawer"
        style={{ width: `min(${width}px, 96vw)` }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ax-drawer__header">
          <div className="ax-card__title">{title}</div>
          <button type="button" className="ax-toast__dismiss" onClick={onClose} aria-label="Close drawer">
            <X size={16} />
          </button>
        </header>
        <div className="ax-drawer__body">{children}</div>
        {footer ? <footer className="ax-drawer__footer">{footer}</footer> : null}
      </aside>
    </div>,
    document.body,
  );
}

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Modal({ open, onClose, title, children, footer, width = 640 }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="ax-modal-overlay" role="presentation" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={cx("ax-modal")}
        style={{ width: `min(${width}px, 92vw)` }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ax-modal__header">
          <div className="ax-card__title">{title}</div>
          <button type="button" className="ax-toast__dismiss" onClick={onClose} aria-label="Close modal">
            <X size={16} />
          </button>
        </header>
        <div className="ax-modal__body">{children}</div>
        {footer ? <footer className="ax-modal__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}