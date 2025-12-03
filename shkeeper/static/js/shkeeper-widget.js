/**
 * TorPay Payment Widget
 *
 * A lightweight, embeddable payment widget for accepting cryptocurrency payments.
 * https://torpay.me
 *
 * Usage:
 *   <script src="https://torpay.me/static/js/shkeeper-widget.js"></script>
 *   <script>
 *     SHKeeper.init({
 *       apiKey: 'your-merchant-api-key',
 *       baseUrl: 'https://api.torpay.me'
 *     });
 *
 *     // Create a payment button
 *     SHKeeper.createButton('#payment-button', {
 *       amount: 99.99,
 *       currency: 'USD',
 *       crypto: 'BTC',
 *       orderId: 'order-123',
 *       onSuccess: function(data) { console.log('Payment initiated', data); },
 *       onError: function(error) { console.error('Error', error); }
 *     });
 *   </script>
 */

(function(window) {
  'use strict';

  var SHKeeper = {
    config: {
      apiKey: null,
      baseUrl: '',
      theme: 'light'
    },

    /**
     * Initialize the widget with configuration
     */
    init: function(options) {
      if (!options.apiKey) {
        console.error('SHKeeper: apiKey is required');
        return;
      }
      this.config.apiKey = options.apiKey;
      this.config.baseUrl = (options.baseUrl || '').replace(/\/$/, '');
      this.config.theme = options.theme || 'light';

      // Inject styles
      this._injectStyles();
    },

    /**
     * Create a payment request via API
     */
    createPayment: function(options, callback) {
      var self = this;

      if (!this.config.apiKey) {
        callback({ error: 'Widget not initialized. Call SHKeeper.init() first.' });
        return;
      }

      var crypto = options.crypto || 'BTC';
      var payload = {
        external_id: options.orderId || options.externalId || ('order-' + Date.now()),
        fiat: options.currency || 'USD',
        amount: parseFloat(options.amount),
        callback_url: options.callbackUrl || null
      };

      var xhr = new XMLHttpRequest();
      xhr.open('POST', this.config.baseUrl + '/api/v1/' + crypto + '/payment_request', true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-Shkeeper-Api-Key', this.config.apiKey);

      xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
          try {
            var response = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) {
              callback(null, response);
            } else {
              callback(response);
            }
          } catch (e) {
            callback({ error: 'Failed to parse response', details: xhr.responseText });
          }
        }
      };

      xhr.onerror = function() {
        callback({ error: 'Network error' });
      };

      xhr.send(JSON.stringify(payload));
    },

    /**
     * Create a payment button that opens the payment modal
     */
    createButton: function(selector, options) {
      var self = this;
      var container = typeof selector === 'string' ? document.querySelector(selector) : selector;

      if (!container) {
        console.error('SHKeeper: Container element not found:', selector);
        return;
      }

      var button = document.createElement('button');
      button.className = 'shkeeper-btn';
      button.innerHTML = this._getButtonHTML(options);

      button.addEventListener('click', function(e) {
        e.preventDefault();
        self.openPaymentModal(options);
      });

      container.appendChild(button);
      return button;
    },

    /**
     * Open the payment modal
     */
    openPaymentModal: function(options) {
      var self = this;

      // Show loading modal
      var modal = this._createModal();
      modal.content.innerHTML = this._getLoadingHTML();

      // Create payment request
      this.createPayment(options, function(error, data) {
        if (error) {
          modal.content.innerHTML = self._getErrorHTML(error.message || error.error || 'Payment failed');
          if (options.onError) options.onError(error);
          return;
        }

        // Show payment details
        modal.content.innerHTML = self._getPaymentHTML(data, options);
        self._setupPaymentModal(modal, data, options);

        if (options.onSuccess) options.onSuccess(data);
      });
    },

    /**
     * Check payment status
     */
    checkStatus: function(invoiceId, callback) {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', this.config.baseUrl + '/api/v1/invoices/' + invoiceId, true);
      xhr.setRequestHeader('X-Shkeeper-Api-Key', this.config.apiKey);

      xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
          try {
            var response = JSON.parse(xhr.responseText);
            callback(null, response);
          } catch (e) {
            callback({ error: 'Failed to parse response' });
          }
        }
      };

      xhr.send();
    },

    // Private methods

    _injectStyles: function() {
      if (document.getElementById('shkeeper-styles')) return;

      var styles = document.createElement('style');
      styles.id = 'shkeeper-styles';
      styles.textContent = `
        .shkeeper-btn {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 12px 24px;
          background: linear-gradient(135deg, #f7931a 0%, #ff9500 100%);
          color: white;
          border: none;
          border-radius: 8px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.2s, box-shadow 0.2s;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .shkeeper-btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(247, 147, 26, 0.4);
        }
        .shkeeper-btn svg {
          width: 20px;
          height: 20px;
        }
        .shkeeper-modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 999999;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .shkeeper-modal {
          background: white;
          border-radius: 16px;
          max-width: 420px;
          width: 90%;
          max-height: 90vh;
          overflow-y: auto;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          position: relative;
        }
        .shkeeper-modal-close {
          position: absolute;
          top: 12px;
          right: 12px;
          width: 32px;
          height: 32px;
          border: none;
          background: #f0f0f0;
          border-radius: 50%;
          cursor: pointer;
          font-size: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .shkeeper-modal-close:hover {
          background: #e0e0e0;
        }
        .shkeeper-modal-content {
          padding: 24px;
        }
        .shkeeper-header {
          text-align: center;
          margin-bottom: 24px;
        }
        .shkeeper-header h3 {
          margin: 0 0 8px 0;
          font-size: 20px;
          color: #333;
        }
        .shkeeper-amount {
          font-size: 32px;
          font-weight: 700;
          color: #f7931a;
        }
        .shkeeper-crypto-amount {
          font-size: 14px;
          color: #666;
          margin-top: 4px;
        }
        .shkeeper-qr-container {
          text-align: center;
          margin: 24px 0;
        }
        .shkeeper-qr-container img {
          max-width: 200px;
          border-radius: 8px;
        }
        .shkeeper-address-container {
          background: #f8f9fa;
          border-radius: 8px;
          padding: 16px;
          margin: 16px 0;
        }
        .shkeeper-address-label {
          font-size: 12px;
          color: #666;
          margin-bottom: 8px;
        }
        .shkeeper-address {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .shkeeper-address code {
          flex: 1;
          font-size: 12px;
          word-break: break-all;
          background: white;
          padding: 8px;
          border-radius: 4px;
          border: 1px solid #e0e0e0;
        }
        .shkeeper-copy-btn {
          padding: 8px 12px;
          background: #f7931a;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 12px;
          white-space: nowrap;
        }
        .shkeeper-copy-btn:hover {
          background: #e8850f;
        }
        .shkeeper-status {
          text-align: center;
          padding: 12px;
          border-radius: 8px;
          margin-top: 16px;
        }
        .shkeeper-status.pending {
          background: #fff3cd;
          color: #856404;
        }
        .shkeeper-status.paid {
          background: #d4edda;
          color: #155724;
        }
        .shkeeper-status.expired {
          background: #f8d7da;
          color: #721c24;
        }
        .shkeeper-timer {
          font-size: 14px;
          color: #666;
          text-align: center;
          margin-top: 12px;
        }
        .shkeeper-loading {
          text-align: center;
          padding: 40px;
        }
        .shkeeper-spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #f0f0f0;
          border-top-color: #f7931a;
          border-radius: 50%;
          animation: shkeeper-spin 1s linear infinite;
          margin: 0 auto 16px;
        }
        @keyframes shkeeper-spin {
          to { transform: rotate(360deg); }
        }
        .shkeeper-error {
          text-align: center;
          padding: 24px;
          color: #dc3545;
        }
        .shkeeper-cryptos {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin: 16px 0;
          justify-content: center;
        }
        .shkeeper-crypto-option {
          padding: 8px 16px;
          border: 2px solid #e0e0e0;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }
        .shkeeper-crypto-option:hover,
        .shkeeper-crypto-option.selected {
          border-color: #f7931a;
          background: #fff8f0;
        }
        .shkeeper-footer {
          text-align: center;
          padding-top: 16px;
          border-top: 1px solid #e0e0e0;
          margin-top: 16px;
        }
        .shkeeper-footer a {
          color: #666;
          font-size: 12px;
          text-decoration: none;
        }
      `;
      document.head.appendChild(styles);
    },

    _createModal: function() {
      var self = this;

      var overlay = document.createElement('div');
      overlay.className = 'shkeeper-modal-overlay';

      var modal = document.createElement('div');
      modal.className = 'shkeeper-modal';

      var closeBtn = document.createElement('button');
      closeBtn.className = 'shkeeper-modal-close';
      closeBtn.innerHTML = '&times;';
      closeBtn.addEventListener('click', function() {
        self._closeModal(overlay);
      });

      var content = document.createElement('div');
      content.className = 'shkeeper-modal-content';

      modal.appendChild(closeBtn);
      modal.appendChild(content);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
          self._closeModal(overlay);
        }
      });

      return { overlay: overlay, modal: modal, content: content };
    },

    _closeModal: function(overlay) {
      if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
    },

    _getButtonHTML: function(options) {
      var cryptoIcon = this._getCryptoIcon(options.crypto || 'BTC');
      var text = options.buttonText || 'Pay with Crypto';
      if (options.amount) {
        text = 'Pay $' + parseFloat(options.amount).toFixed(2);
      }
      return cryptoIcon + '<span>' + text + '</span>';
    },

    _getLoadingHTML: function() {
      return '<div class="shkeeper-loading"><div class="shkeeper-spinner"></div><p>Creating payment...</p></div>';
    },

    _getErrorHTML: function(message) {
      return '<div class="shkeeper-error"><p>' + message + '</p><p>Please try again.</p></div>';
    },

    _getPaymentHTML: function(data, options) {
      var qrUrl = this.config.baseUrl + '/api/v1/' + data.wallet + '/qr/' + data.id;

      return `
        <div class="shkeeper-header">
          <h3>Complete Your Payment</h3>
          <div class="shkeeper-amount">$${parseFloat(data.amount || options.amount).toFixed(2)}</div>
          <div class="shkeeper-crypto-amount">${data.amount_crypto} ${data.wallet}</div>
        </div>

        <div class="shkeeper-qr-container">
          <img src="${qrUrl}" alt="Payment QR Code" />
        </div>

        <div class="shkeeper-address-container">
          <div class="shkeeper-address-label">Send exactly ${data.amount_crypto} ${data.wallet} to:</div>
          <div class="shkeeper-address">
            <code id="shkeeper-address">${data.dest}</code>
            <button class="shkeeper-copy-btn" onclick="SHKeeper._copyAddress()">Copy</button>
          </div>
        </div>

        <div class="shkeeper-status pending" id="shkeeper-status">
          Waiting for payment...
        </div>

        <div class="shkeeper-timer" id="shkeeper-timer">
          Invoice expires in <span id="shkeeper-countdown">15:00</span>
        </div>

        <div class="shkeeper-footer">
          <a href="https://torpay.me" target="_blank">Powered by TorPay</a>
        </div>
      `;
    },

    _setupPaymentModal: function(modal, data, options) {
      var self = this;
      var expiresAt = new Date(data.expires_at || (Date.now() + 15 * 60 * 1000));

      // Countdown timer
      var countdownEl = document.getElementById('shkeeper-countdown');
      var timerInterval = setInterval(function() {
        var now = new Date();
        var diff = expiresAt - now;

        if (diff <= 0) {
          clearInterval(timerInterval);
          countdownEl.textContent = 'Expired';
          document.getElementById('shkeeper-status').className = 'shkeeper-status expired';
          document.getElementById('shkeeper-status').textContent = 'Invoice expired';
          return;
        }

        var minutes = Math.floor(diff / 60000);
        var seconds = Math.floor((diff % 60000) / 1000);
        countdownEl.textContent = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
      }, 1000);

      // Poll for payment status
      var statusInterval = setInterval(function() {
        self.checkStatus(data.id, function(error, response) {
          if (error) return;

          var statusEl = document.getElementById('shkeeper-status');
          if (!statusEl) {
            clearInterval(statusInterval);
            return;
          }

          if (response.status === 'paid' || response.status === 'paid-expired') {
            clearInterval(statusInterval);
            clearInterval(timerInterval);
            statusEl.className = 'shkeeper-status paid';
            statusEl.textContent = 'Payment received! Thank you.';

            if (options.onPaymentComplete) {
              options.onPaymentComplete(response);
            }
          }
        });
      }, 5000);

      // Cleanup on modal close
      modal.overlay.addEventListener('click', function(e) {
        if (e.target === modal.overlay) {
          clearInterval(statusInterval);
          clearInterval(timerInterval);
        }
      });
    },

    _copyAddress: function() {
      var addressEl = document.getElementById('shkeeper-address');
      if (addressEl) {
        navigator.clipboard.writeText(addressEl.textContent).then(function() {
          var btn = document.querySelector('.shkeeper-copy-btn');
          if (btn) {
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = 'Copy'; }, 2000);
          }
        });
      }
    },

    _getCryptoIcon: function(crypto) {
      // Bitcoin icon as default
      return '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v2h1c1.1 0 2 .9 2 2v2c0 1.1-.9 2-2 2h-1v2h-2v-2H9v-2h2v-2H9v-2h2V7zm2 4v2h1v-2h-1z"/></svg>';
    }
  };

  // Expose to global scope
  window.SHKeeper = SHKeeper;

})(window);
