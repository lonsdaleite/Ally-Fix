import { definePlugin } from "@decky/api";
import { FaWrench } from "react-icons/fa";
import { AllyFixPanel } from "./components/AllyFixPanel";
import { stopLayoutPatch, syncLayoutPatch } from "./gamepadLayout";
import { connectEvents, disconnectEvents, store } from "./store";

export default definePlugin(() => {
  // The UI half of the Gamepad Layout Fix lives in this process: follow the toggle.
  const unsubscribe = store.subscribe(() => void syncLayoutPatch());
  connectEvents();
  return {
    name: "Ally Fix",
    icon: <FaWrench />,
    content: <AllyFixPanel />,
    onDismount() {
      unsubscribe();
      stopLayoutPatch();
      disconnectEvents();
    },
  };
});
