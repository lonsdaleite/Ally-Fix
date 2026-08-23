import { ButtonItem, Focusable, PanelSectionRow } from "@decky/ui";
import { useState, type ReactNode } from "react";
import { RiArrowDownSFill, RiArrowUpSFill } from "react-icons/ri";

export function Collapsible({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
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
