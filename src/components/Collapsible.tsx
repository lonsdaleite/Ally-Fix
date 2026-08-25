import { ButtonItem, Focusable, PanelSectionRow } from "@decky/ui";
import { useState, type ReactNode } from "react";
import { RiArrowDownSFill, RiArrowUpSFill } from "react-icons/ri";

// Open/closed state lives outside the component: Steam unmounts the whole QAM panel when
// the controller reconnects (every InputPlumber restart), and it should come back as it was.
const openState = new Map<string, boolean>();

export function Collapsible({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const [open, setOpenState] = useState(openState.get(id) ?? false);
  const setOpen = (v: boolean) => {
    openState.set(id, v);
    setOpenState(v);
  };
  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" bottomSeparator={open ? "none" : "standard"} onClick={() => setOpen(!open)}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            {open ? <RiArrowUpSFill /> : <RiArrowDownSFill />}
            {title}
          </span>
        </ButtonItem>
      </PanelSectionRow>
      {open && <Focusable style={{ paddingLeft: 8 }}>{children}</Focusable>}
    </>
  );
}
