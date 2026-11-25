/**
 * "Draw on Wall" (experimental): tap holds in the picture to colour them, and send
 * the result to the board's LEDs over Web Bluetooth.
 *
 * Expects these globals from the template: colors, ledColors, placementPositions.
 * Uses getBluetoothPacket / sendBluetoothPacket / disconnectBoard from bluetooth.js.
 */

const board = new URLSearchParams(window.location.search).get("board");
const statusElement = document.getElementById("span-status");
const liveSwitch = document.getElementById("switch-live");

function setStatus(text, style = "secondary") {
  statusElement.textContent = text;
  statusElement.className = `badge text-bg-${style}`;
}

function onDrawCircleClick(circleElement) {
  const colorIds = colors.map((colorRow) => colorRow[0]);
  const screenColors = colors.map((colorRow) => colorRow[1]);
  const nextIndex = screenColors.indexOf(circleElement.getAttribute("stroke")) + 1;
  if (nextIndex >= screenColors.length) {
    circleElement.setAttribute("stroke-opacity", 0.0);
    circleElement.setAttribute("stroke", "black");
  } else {
    circleElement.setAttribute("stroke", screenColors[nextIndex]);
    circleElement.setAttribute("stroke-opacity", 1.0);
    circleElement.setAttribute("data-color-id", colorIds[nextIndex]);
  }
  if (liveSwitch.checked) {
    sendToWall();
  }
}

function getDrawnFrames() {
  const frames = [];
  document
    .getElementById("svg-climb")
    .querySelectorAll('circle[stroke-opacity="1"]')
    .forEach((circle) => {
      const holdId = circle.id.split("-")[1];
      frames.push(`p${holdId}r${circle.getAttribute("data-color-id")}`);
    });
  return frames.join("");
}

// Bluetooth can only do one write at a time. If the user taps faster than we can
// send, remember that another send is needed and send the latest drawing afterwards.
let sending = false;
let sendAgain = false;

async function sendToWall(frames = null) {
  if (sending) {
    sendAgain = true;
    return;
  }
  sending = true;
  setStatus("Sending…", "info");
  try {
    do {
      sendAgain = false;
      const packet = getBluetoothPacket(
        frames === null ? getDrawnFrames() : frames,
        placementPositions,
        ledColors
      );
      await sendBluetoothPacket(board, packet);
    } while (sendAgain);
    setStatus("Connected", "success");
  } catch (error) {
    const message = bluetoothErrorMessage(error);
    setStatus(message ? "Error" : "Not connected", message ? "danger" : "secondary");
    liveSwitch.checked = false;
    if (message) {
      alert(message);
    }
  } finally {
    sending = false;
  }
}

function resetDrawing() {
  document
    .getElementById("svg-climb")
    .querySelectorAll("circle")
    .forEach((circle) => {
      circle.setAttribute("stroke-opacity", 0.0);
      circle.setAttribute("stroke", "black");
    });
}

document.getElementById("button-illuminate").addEventListener("click", () => sendToWall());

document.getElementById("button-clear-wall").addEventListener("click", () => {
  resetDrawing();
  sendToWall("");
});

document.getElementById("button-reset-holds").addEventListener("click", () => {
  resetDrawing();
  if (liveSwitch.checked) {
    sendToWall();
  }
});

document.getElementById("button-disconnect").addEventListener("click", () => {
  disconnectBoard();
  liveSwitch.checked = false;
  setStatus("Not connected");
});

liveSwitch.addEventListener("change", () => {
  if (liveSwitch.checked) {
    sendToWall();
  }
});

if (!navigator.bluetooth) {
  setStatus("Web Bluetooth not supported in this browser", "warning");
}

const backAnchor = document.getElementById("anchor-back");
backAnchor.href = location.origin;
