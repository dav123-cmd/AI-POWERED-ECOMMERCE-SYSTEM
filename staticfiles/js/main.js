/* ============================================================
   ShopAI — Main JavaScript
   ============================================================ */
const canvas = document.getElementById('c-particles');
  const ctx = canvas.getContext('2d');

  let particles = [];

  function init() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 1.0,
      vy: (Math.random() - 0.5) * 1.0,
      size: Math.random() * 2 + 0.5
    }));
  }

  window.addEventListener('resize', init);
  init();

  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    particles.forEach((p, i) => {
      // Move
      p.x += p.vx;
      p.y += p.vy;
      
      // Bounce
      if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
      
      // Draw particle
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.fill();

      // Connect particles
      for (let j = i + 1; j < particles.length; j++) {
        let p2 = particles[j];
        let dx = p.x - p2.x;
        let dy = p.y - p2.y;
        let dist = Math.sqrt(dx * dx + dy * dy);
        
        if (dist < 100) {
          ctx.strokeStyle = `rgba(0, 242, 254, ${0.2 * (1 - dist/100)})`;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();
        }
      }
    });
    requestAnimationFrame(animate);
  }
  
  animate();
// ── CSRF Helper ───────────────────────────────────────────
function getCookie(name) {
  let value = null;
  document.cookie.split(';').forEach(c => {
    const [k, v] = c.trim().split('=');
    if (k === name) value = decodeURIComponent(v);
  });
  return value;
}

// ── Cursor Glow ───────────────────────────────────────────
const cursorGlow = document.getElementById('cursorGlow');
if (cursorGlow) {
  document.addEventListener('mousemove', e => {
    cursorGlow.style.left = e.clientX + 'px';
    cursorGlow.style.top  = e.clientY + 'px';
  });
}

// ── Navbar Scroll Effect ──────────────────────────────────
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  if (navbar) navbar.classList.toggle('scrolled', window.scrollY > 60);
});

// ── Search Overlay ────────────────────────────────────────
const searchOverlay  = document.getElementById('searchOverlay');
const searchOpenBtn  = document.getElementById('searchOpenBtn');
const searchClose    = document.getElementById('searchClose');
const searchInput    = document.getElementById('searchInput');

function openSearch() {
  if (!searchOverlay) return;
  searchOverlay.classList.add('open');
  setTimeout(() => searchInput?.focus(), 100);
}

function closeSearch() {
  searchOverlay?.classList.remove('open');
}

searchOpenBtn?.addEventListener('click', openSearch);
searchClose?.addEventListener('click', closeSearch);
searchOverlay?.addEventListener('click', e => {
  if (e.target === searchOverlay) closeSearch();
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSearch(); }
  if (e.key === 'Escape') { closeSearch(); closeUserDropdown(); }
});

// AI Search with debounce
let searchTimeout;
searchInput?.addEventListener('input', e => {
  clearTimeout(searchTimeout);
  const q = e.target.value.trim();
  if (!q) { document.getElementById('searchSuggestions').innerHTML = ''; return; }
  searchTimeout = setTimeout(() => aiSearch(q), 350);
});

async function aiSearch(query) {
  try {
    const res  = await fetch(`/ai/search/suggest/?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderSearchSuggestions(data.suggestions || []);
  } catch { /* silent */ }
}

function renderSearchSuggestions(items) {
  const container = document.getElementById('searchSuggestions');
  if (!container || !items.length) { container && (container.innerHTML = ''); return; }
  container.innerHTML = `
    <div style="
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
    ">
      ${items.map(item => `
        <a href="/search/?q=${encodeURIComponent(item.query || item)}" style="
          display: flex; align-items: center; gap: 0.75rem;
          padding: 0.875rem 1.25rem;
          color: var(--text-secondary);
          transition: var(--transition);
          border-bottom: 1px solid var(--border);
        "
        onmouseover="this.style.background='var(--bg-elevated)';this.style.color='var(--text-primary)'"
        onmouseout="this.style.background='';this.style.color='var(--text-secondary)'"
        >
          <i class="fa-solid fa-magnifying-glass" style="color:var(--accent-gold);font-size:0.8rem;"></i>
          ${item.label || item}
        </a>
      `).join('')}
    </div>
  `;
}

// ── User Dropdown ─────────────────────────────────────────
const userMenuToggle = document.getElementById('userMenuToggle');
const userDropdown   = document.getElementById('userDropdown');

function closeUserDropdown() {
  userDropdown?.classList.remove('open');
}

userMenuToggle?.addEventListener('click', e => {
  e.stopPropagation();
  userDropdown?.classList.toggle('open');
});

document.addEventListener('click', e => {
  if (!userMenuToggle?.contains(e.target) && !userDropdown?.contains(e.target)) {
    closeUserDropdown();
  }
});

// ── Toast Notifications ───────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('messagesContainer') ||
    (() => {
      const d = document.createElement('div');
      d.className = 'messages-container';
      d.id = 'messagesContainer';
      document.body.appendChild(d);
      return d;
    })();

  const icons = {
    success: 'fa-circle-check',
    error:   'fa-circle-xmark',
    warning: 'fa-triangle-exclamation',
    info:    'fa-circle-info',
  };

  const toast = document.createElement('div');
  toast.className = `message message--${type}`;
  toast.innerHTML = `
    <span class="message__icon"><i class="fa-solid ${icons[type] || icons.info}"></i></span>
    <span class="message__text">${message}</span>
    <button class="message__close" onclick="this.parentElement.remove()">
      <i class="fa-solid fa-xmark"></i>
    </button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

// ── Auto-dismiss messages ─────────────────────────────────
document.querySelectorAll('[data-auto-dismiss]').forEach(el => {
  setTimeout(() => el.remove(), 5000);
});

// ── Add to Cart ───────────────────────────────────────────
async function addToCart(productId, qty = 1, btn = null) {
  if (btn) {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    btn.disabled  = true;

    try {
      const res  = await fetch('/orders/cart/add/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ product_id: productId, quantity: qty }),
      });
      const data = await res.json();

      if (data.success) {
        showToast(data.message || 'Added to cart! ', 'success');
        // Update cart badge
        document.querySelectorAll('.navbar__badge').forEach(badge => {
          if (badge.closest('.navbar__icon-btn')?.querySelector('.fa-bag-shopping')) {
            badge.textContent = data.cart_count;
            badge.style.display = data.cart_count > 0 ? 'flex' : 'none';
          }
        });
        btn.innerHTML = '<i class="fa-solid fa-check"></i>';
        setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 1500);
      } else {
        showToast(data.error || 'Could not add to cart.', 'error');
        btn.innerHTML = original;
        btn.disabled  = false;
      }
    } catch {
      showToast('Network error. Please try again.', 'error');
      btn.innerHTML = original;
      btn.disabled  = false;
    }
  }
}

// ── Toggle Wishlist ───────────────────────────────────────
async function toggleWishlist(productId, btn) {
  try {
    const res  = await fetch('/wishlist/toggle/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ product_id: productId }),
    });
    const data = await res.json();
    if (data.added) {
      btn.style.color = '#ef4444';
      showToast('Added to wishlist ', 'success');
    } else {
      btn.style.color = '';
      showToast('Removed from wishlist', 'info');
    }
  } catch {
    showToast('Please sign in to use wishlist.', 'warning');
  }
}

// ── Image Lazy Loading ────────────────────────────────────
const lazyImages = document.querySelectorAll('img[data-src]');
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
        observer.unobserve(img);
      }
    });
  }, { rootMargin: '50px' });
  lazyImages.forEach(img => observer.observe(img));
}

// ── Scroll Animations ─────────────────────────────────────
const animateOnScroll = document.querySelectorAll('[data-animate]');
if (animateOnScroll.length && 'IntersectionObserver' in window) {
  const animObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity  = '1';
        entry.target.style.transform = 'translateY(0)';
        animObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  animateOnScroll.forEach((el, i) => {
    el.style.opacity   = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = `opacity 0.6s ease ${i * 0.08}s, transform 0.6s ease ${i * 0.08}s`;
    animObserver.observe(el);
  });
}

// ── Product Image Zoom ────────────────────────────────────
document.querySelectorAll('.product-image-zoom').forEach(img => {
  img.addEventListener('mousemove', e => {
    const rect = img.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width)  * 100;
    const y = ((e.clientY - rect.top)  / rect.height) * 100;
    img.style.transformOrigin = `${x}% ${y}%`;
    img.style.transform = 'scale(1.5)';
  });
  img.addEventListener('mouseleave', () => {
    img.style.transform = 'scale(1)';
  });
});

// ── Format Currency ───────────────────────────────────────
function formatCurrency(amount, currency = 'KES') {
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency }).format(amount);
}

console.log('%cShopAI', 'font-size:24px; font-weight:bold; color:#c9a84c;');
console.log('%cAI-Powered E-commerce Platform', 'color:#9996a0;');

// ── Quick View Modal ──────────────────────────────────────
function openQuickView(slug, e) {
  e.preventDefault();
  let modal = document.getElementById('quickViewModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'quickViewModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);z-index:4000;display:flex;align-items:center;justify-content:center;padding:1rem;';
    modal.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-xl);max-width:680px;width:100%;position:relative;overflow:hidden;box-shadow:var(--shadow-lg);">
        <button onclick="document.getElementById('quickViewModal').remove()" style="position:absolute;top:1rem;right:1rem;z-index:1;width:32px;height:32px;background:var(--bg-elevated);border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">✕</button>
        <div id="quickViewContent" style="min-height:200px;display:flex;align-items:center;justify-content:center;">
          <div style="font-size:2rem;animation:spin 1s linear infinite;">⟳</div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', evt => { if (evt.target === modal) modal.remove(); });
  }
  fetch(`/shop/${slug}/quick/`).then(r => r.text()).then(html => {
    document.getElementById('quickViewContent').innerHTML = html;
  });
}

// ── Update URL params without reload ─────────────────────
function updateParam(key, value) {
  const url = new URL(window.location);
  if (value) url.searchParams.set(key, value);
  else url.searchParams.delete(key);
  window.history.pushState({}, '', url);
}

/* Analytics Dashboard — extracted script
   Originally inlined in dashboard.html {% block extra_js %}

   Expects the following globals to be defined by a small inline
   <script> block in the template before this file is loaded:
     - window.dashboardChartData   (chart series data)
     - window.dashboardCategoryData (category breakdown data)
     - window.dashboardForecastUrl  (run_forecast endpoint URL)
*/

(function () {
  // ── Chart.js defaults ─────────────────────────────────────
  Chart.defaults.color = '#9996A0';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.07)';
  Chart.defaults.font.family = "'DM Sans', sans-serif";

  const chartData = window.dashboardChartData;
  const catData = window.dashboardCategoryData;

  // ── Revenue + Forecast Chart ──────────────────────────────
  const revCanvas = document.getElementById('revenueChart');
  if (revCanvas) {
    const revCtx = revCanvas.getContext('2d');

    const revGrad = revCtx.createLinearGradient(0, 0, 0, 300);
    revGrad.addColorStop(0, 'rgba(201,168,76,0.3)');
    revGrad.addColorStop(1, 'rgba(201,168,76,0.0)');

    const fcastGrad = revCtx.createLinearGradient(0, 0, 0, 300);
    fcastGrad.addColorStop(0, 'rgba(0,212,255,0.15)');
    fcastGrad.addColorStop(1, 'rgba(0,212,255,0.0)');

    new Chart(revCtx, {
      type: 'line',
      data: {
        labels: [...chartData.labels, ...chartData.forecast_labels],
        datasets: [
          {
            label: 'Actual Revenue',
            data: [...chartData.revenues, ...Array(chartData.forecast_labels.length).fill(null)],
            borderColor: '#C9A84C',
            backgroundColor: revGrad,
            fill: true,
            tension: 0.4,
            pointRadius: 3,
            pointBackgroundColor: '#C9A84C',
            borderWidth: 2,
          },
          {
            label: 'AI Forecast',
            data: [...Array(chartData.labels.length).fill(null), ...chartData.forecast_revenues],
            borderColor: '#00D4FF',
            backgroundColor: fcastGrad,
            fill: true,
            tension: 0.4,
            borderDash: [6, 3],
            pointRadius: 3,
            pointBackgroundColor: '#00D4FF',
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#13131e',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            callbacks: {
              label: ctx => (ctx.raw !== null ? ` KES ${Math.round(ctx.raw).toLocaleString()}` : ''),
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } },
          y: {
            ticks: { callback: v => 'KES ' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v) },
          },
        },
      },
    });
  }

  // ── Orders Bar Chart ──────────────────────────────────────
  const ordersCanvas = document.getElementById('ordersChart');
  if (ordersCanvas) {
    new Chart(ordersCanvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Orders',
          data: chartData.orders,
          backgroundColor: 'rgba(0,212,255,0.5)',
          borderColor: 'rgba(0,212,255,0.8)',
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
          y: { beginAtZero: true, ticks: { stepSize: 1 } },
        },
      },
    });
  }

  // ── Category Pie Chart ────────────────────────────────────
  const categoryCanvas = document.getElementById('categoryChart');
  if (categoryCanvas && catData.length) {
    new Chart(categoryCanvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: catData.map(c => c.category__name || 'Other'),
        datasets: [{
          data: catData.map(c => c.total),
          backgroundColor: ['#C9A84C', '#00D4FF', '#7C3AED', '#10B981', '#F97316', '#EF4444', '#8B5CF6', '#06B6D4'],
          borderWidth: 2,
          borderColor: '#13131e',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: ctx => ` KES ${Math.round(ctx.raw).toLocaleString()}`,
            },
          },
        },
        cutout: '65%',
      },
    });
  }

  // ── Actions ───────────────────────────────────────────────
  window.runForecast = async function runForecast() {
    showToast('<i class="fa-solid fa-brain"></i> Running LSTM forecast...', 'info');
    const res = await fetch(window.dashboardForecastUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    });
    const data = await res.json();
    if (data.success) {
      showToast(`<i class="fa-solid fa-circle-check"></i> ${data.message}`, 'success');
      setTimeout(() => window.location.reload(), 1500);
    } else {
      showToast(`<i class="fa-solid fa-circle-xmark"></i> ${data.error}`, 'error');
    }
  };
})();