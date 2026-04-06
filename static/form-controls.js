(function initSunnyVibeNumberInputs() {
  const selector = 'input[type="number"]:not([data-number-enhanced]):not([data-no-number-controls])';

  const parseNumber = (value) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const decimalPlaces = (value) => {
    const text = String(value);
    if (!text.includes('.')) {
      return 0;
    }
    return text.split('.')[1].length;
  };

  const normalizeNumber = (value, decimals) => {
    if (decimals <= 0) {
      return String(Math.round(value));
    }
    return value.toFixed(decimals).replace(/\.?0+$/, '');
  };

  const syncButtons = (input, buttons) => {
    const disabled = input.disabled || input.readOnly;
    buttons.forEach((button) => {
      button.disabled = disabled;
    });
  };

  const changeValue = (input, direction) => {
    if (input.disabled || input.readOnly) {
      return;
    }

    const step = input.step && input.step !== 'any' ? parseNumber(input.step) : 1;
    const min = input.min !== '' ? parseNumber(input.min) : null;
    const max = input.max !== '' ? parseNumber(input.max) : null;
    const current = parseNumber(input.value);
    const safeStep = step && step > 0 ? step : 1;
    let next = (current ?? min ?? 0) + (direction * safeStep);

    if (min !== null && next < min) {
      next = min;
    }
    if (max !== null && next > max) {
      next = max;
    }

    const decimals = Math.max(decimalPlaces(safeStep), decimalPlaces(next));
    input.value = normalizeNumber(next, decimals);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const enhanceInput = (input) => {
    if (!(input instanceof HTMLInputElement) || input.dataset.numberEnhanced === 'true') {
      return;
    }

    input.dataset.numberEnhanced = 'true';
    input.classList.add('number-input');

    if (input.parentElement && input.parentElement.classList.contains('number-wrap')) {
      return;
    }

    const wrapper = document.createElement('span');
    wrapper.className = 'number-wrap';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const buttons = document.createElement('span');
    buttons.className = 'number-buttons';

    const upButton = document.createElement('button');
    upButton.className = 'number-btn';
    upButton.type = 'button';
    upButton.textContent = '▲';
    upButton.setAttribute('aria-label', 'Augmenter la valeur');

    const downButton = document.createElement('button');
    downButton.className = 'number-btn';
    downButton.type = 'button';
    downButton.textContent = '▼';
    downButton.setAttribute('aria-label', 'Diminuer la valeur');

    buttons.append(upButton, downButton);
    wrapper.appendChild(buttons);

    upButton.addEventListener('click', () => changeValue(input, 1));
    downButton.addEventListener('click', () => changeValue(input, -1));
    syncButtons(input, [upButton, downButton]);

    const stateObserver = new MutationObserver(() => {
      syncButtons(input, [upButton, downButton]);
    });
    stateObserver.observe(input, { attributes: true, attributeFilter: ['disabled', 'readonly'] });
  };

  const enhanceAll = (root = document) => {
    root.querySelectorAll(selector).forEach(enhanceInput);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => enhanceAll());
  } else {
    enhanceAll();
  }

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) {
          return;
        }
        if (node.matches(selector)) {
          enhanceInput(node);
        }
        enhanceAll(node);
      });
    });
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
}());
