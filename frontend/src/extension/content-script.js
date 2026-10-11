// Runs only after the user presses "Escoger texto" in the popup.
const controller = globalThis.__scanTrueSelectionController ??= createSelectionController();
controller.start();

function createSelectionController() {
  let active = false;

  function stop() {
    active = false;
    document.removeEventListener('mouseup', capture);
    document.removeEventListener('keyup', capture);
    document.removeEventListener('keydown', cancel);
  }

  function selectedText() {
    const element = document.activeElement;
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      if (element instanceof HTMLInputElement && element.type === 'password') return '';
      const { selectionStart, selectionEnd, value } = element;
      if (selectionStart !== null && selectionEnd > selectionStart) {
        return value.slice(selectionStart, selectionEnd);
      }
    }
    return window.getSelection()?.toString() ?? '';
  }

  function capture() {
    if (!active) return;
    const text = selectedText();
    if (!text.trim()) return;
    stop();
    chrome.runtime.sendMessage({ type: 'SELECTION_CAPTURED', text }, () => {
      void chrome.runtime.lastError;
    });
  }

  function cancel(event) {
    if (event.key === 'Escape') stop();
  }

  return {
    start() {
      stop();
      window.getSelection()?.removeAllRanges();
      active = true;
      document.addEventListener('mouseup', capture);
      document.addEventListener('keyup', capture);
      document.addEventListener('keydown', cancel);
    },
  };
}
