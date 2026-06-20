"use client";

import { useEffect, useState } from "react";
import { Modal, Button, Stack } from "../ui";
import { useOperator } from "../../providers/operator-provider";
import { useToast } from "../../providers/toast-provider";

export function OperatorSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { baseUrl, token, actor, setSettings } = useOperator();
  const [draftBase, setDraftBase] = useState(baseUrl);
  const [draftToken, setDraftToken] = useState(token);
  const [draftActor, setDraftActor] = useState(actor);
  const toast = useToast();

  // Sync the draft with the current value each time the modal opens.
  useEffect(() => {
    if (!open) return;
    setDraftBase(baseUrl);
    setDraftToken(token);
    setDraftActor(actor);
  }, [open, baseUrl, token, actor]);

  function save() {
    setSettings({ baseUrl: draftBase.trim(), token: draftToken.trim(), actor: draftActor.trim() || "operator" });
    toast.push({
      title: "Operator settings saved",
      message: draftBase ? `Base: ${draftBase}` : "Using fixture mode",
      tone: "good",
    });
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Operator settings"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save}>Save</Button>
        </>
      }
    >
      <Stack gap={4}>
        <Stack gap={1}>
          <label className="dim" htmlFor="op-base-url">API base URL</label>
          <input
            id="op-base-url"
            type="url"
            className="ax-input"
            placeholder="http://127.0.0.1:8000"
            value={draftBase}
            onChange={(e) => setDraftBase(e.target.value)}
          />
        </Stack>
        <Stack gap={1}>
          <label className="dim" htmlFor="op-token">Operator token (Bearer)</label>
          <input
            id="op-token"
            type="password"
            className="ax-input"
            placeholder="op_…"
            value={draftToken}
            onChange={(e) => setDraftToken(e.target.value)}
            autoComplete="off"
          />
        </Stack>
        <Stack gap={1}>
          <label className="dim" htmlFor="op-actor">Actor name (used for command audit)</label>
          <input
            id="op-actor"
            type="text"
            className="ax-input"
            placeholder="operator"
            value={draftActor}
            onChange={(e) => setDraftActor(e.target.value)}
          />
        </Stack>
        <p className="dim" style={{ fontSize: 12 }}>
          Without a base URL the dashboard runs in fixture mode (read-only). Setting a token unlocks write
          commands (instantiate, trigger, approve, reject, edit, promote, set-ring).
        </p>
      </Stack>
    </Modal>
  );
}