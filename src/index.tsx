import { definePlugin } from "@decky/api";
import { FaWrench } from "react-icons/fa";
import { AllyFixPanel } from "./components/AllyFixPanel";
import { connectEvents, disconnectEvents } from "./store";

export default definePlugin(() => {
  connectEvents();
  return {
    name: "Ally Fix",
    icon: <FaWrench />,
    content: <AllyFixPanel />,
    onDismount() {
      disconnectEvents();
    },
  };
});
