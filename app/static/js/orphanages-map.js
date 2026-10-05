/**
 * Help With Food — Interactive Map View (Providers, Receivers, Food Donations, Routes)
 *
 * Drives templates/map/index.html using Leaflet.js and OpenStreetMap.
 */

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function haversineDistanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

// India Bounding Box & Default Coordinates
const INDIA_LAT_MIN = 6.5;
const INDIA_LAT_MAX = 37.5;
const INDIA_LNG_MIN = 68.0;
const INDIA_LNG_MAX = 97.5;
const DEFAULT_INDIA_LAT = 28.6139; // New Delhi
const DEFAULT_INDIA_LNG = 77.2090;

function isInIndia(lat, lng) {
  if (lat == null || lng == null) return false;
  const numLat = parseFloat(lat);
  const numLng = parseFloat(lng);
  if (isNaN(numLat) || isNaN(numLng)) return false;
  return numLat >= INDIA_LAT_MIN && numLat <= INDIA_LAT_MAX && numLng >= INDIA_LNG_MIN && numLng <= INDIA_LNG_MAX;
}

(function () {
  const pageRoot = document.querySelector('[data-page="map-view"]');
  if (!pageRoot) return;

  const mapContainer = document.getElementById('map-container');
  const loadingEl = document.getElementById('map-loading');
  const alertEl = document.getElementById('map-alert');
  const toggleOrphanages = document.getElementById('toggle-orphanages');
  const toggleProviders = document.getElementById('toggle-providers');
  const toggleListings = document.getElementById('toggle-listings');
  const orphanageCountEl = document.getElementById('orphanage-count');
  const providerCountEl = document.getElementById('provider-count');
  const listingsCountEl = document.getElementById('listings-count');
  const searchInput = document.getElementById('map-search-input');
  const locateMeBtn = document.getElementById('map-locate-me-btn');
  const routeBanner = document.getElementById('route-info-banner');
  const routeTitle = document.getElementById('route-title');
  const routeDistanceText = document.getElementById('route-distance-text');
  const clearRouteBtn = document.getElementById('clear-route-btn');

  // URL Query Parameters
  const urlParams = new URLSearchParams(window.location.search);
  const paramLat = parseFloat(urlParams.get('lat'));
  const paramLng = parseFloat(urlParams.get('lng'));

  let initialLat = 20.5937; // India Center
  let initialLng = 78.9629;
  let initialZoom = 5;

  if (!isNaN(paramLat) && !isNaN(paramLng) && isInIndia(paramLat, paramLng)) {
    initialLat = paramLat;
    initialLng = paramLng;
    initialZoom = 13;
  }

  // Initialize Map
  const map = L.map('map-container').setView([initialLat, initialLng], initialZoom);

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  // Custom marker icons
  const orphanageIcon = L.divIcon({
    className: 'custom-map-icon',
    html: `<div style="background-color: #2f7a4f; color: white; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; border: 2px solid white; box-shadow: 0 3px 8px rgba(0,0,0,0.35);">🏠</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  });

  const providerIcon = L.divIcon({
    className: 'custom-map-icon',
    html: `<div style="background-color: #2563eb; color: white; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; border: 2px solid white; box-shadow: 0 3px 8px rgba(0,0,0,0.35);">🏬</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  });

  const donationIcon = L.divIcon({
    className: 'custom-map-icon',
    html: `<div style="background-color: #e8834a; color: white; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; border: 2px solid white; box-shadow: 0 3px 8px rgba(0,0,0,0.35);">🍲</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  });

  const orphanageLayer = L.layerGroup().addTo(map);
  const providerLayer = L.layerGroup().addTo(map);
  const listingsLayer = L.layerGroup().addTo(map);
  const routeLayer = L.layerGroup().addTo(map);

  let activePolyline = null;
  let userLocation = null;

  let allOrphanages = [];
  let allProviders = [];
  let allListings = [];

  function showAlert(msg, type = 'error') {
    alertEl.innerHTML = `<div class="alert alert--${type}">${escapeHtml(msg)}</div>`;
  }

  function drawRoute(lat1, lon1, lat2, lon2, label1, label2) {
    if (activePolyline) {
      map.removeLayer(activePolyline);
    }
    routeLayer.clearLayers();

    const distKm = haversineDistanceKm(lat1, lon1, lat2, lon2);
    const estMin = Math.max(1, Math.round((distKm / 30) * 60)); // ~30 km/h avg speed

    activePolyline = L.polyline([[lat1, lon1], [lat2, lon2]], {
      color: '#2563eb',
      weight: 5,
      opacity: 0.9,
      dashArray: '10, 10',
    }).addTo(map);

    routeTitle.textContent = `📍 Route: ${label1} ➔ ${label2}`;
    routeDistanceText.textContent = `📏 Distance: ${distKm.toFixed(2)} km  |  ⏱️ Est. Travel Time: ~${estMin} min drive`;
    routeBanner.hidden = false;

    map.fitBounds([[lat1, lon1], [lat2, lon2]], { padding: [60, 60] });
  }

  clearRouteBtn.addEventListener('click', () => {
    if (activePolyline) {
      map.removeLayer(activePolyline);
      activePolyline = null;
    }
    routeLayer.clearLayers();
    routeBanner.hidden = true;
  });

  function getEffectiveCoords(item) {
    if (!item) return null;
    let lat = parseFloat(item.latitude);
    let lng = parseFloat(item.longitude);

    if (isNaN(lat) || isNaN(lng) || !isInIndia(lat, lng)) {
      return null;
    }
    return { lat, lng };
  }

  function renderOrphanages(filterText = '') {
    orphanageLayer.clearLayers();
    const query = filterText.toLowerCase();

    const filtered = allOrphanages.filter((r) => {
      const coords = getEffectiveCoords(r);
      if (!coords) return false;
      if (!query) return true;
      const haystack = `${r.organization_name} ${r.city} ${r.state || ''} ${r.address} ${r.pincode || ''} ${r.description}`.toLowerCase();
      return haystack.includes(query);
    });

    orphanageCountEl.textContent = filtered.length;

    filtered.forEach((r) => {
      const coords = getEffectiveCoords(r);
      if (!coords) return;
      const { lat, lng } = coords;

      const isVerified = r.verification_status === 'verified';
      const statusBadge = isVerified
        ? `<span class="badge badge--available" style="font-size:0.75rem;">Verified Orphanage</span>`
        : `<span class="badge badge--pending" style="font-size:0.75rem;">Pending Verification</span>`;

      const phone = r.phone || r.contact_info;
      const email = r.email;
      const locParts = [r.address, r.city, r.state, r.pincode].filter(Boolean);
      const address = locParts.length > 0 ? locParts.join(', ') : 'Address on file';
      const stateLine = r.state
        ? `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> ${escapeHtml(r.state)}</p>`
        : `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> Not specified</p>`;

      const userDist = userLocation
        ? `<p style="color:#2563eb; font-weight:500;">📏 ${haversineDistanceKm(userLocation.lat, userLocation.lng, lat, lng).toFixed(2)} km from you</p>`
        : '';

      const popupContent = `
        <div style="min-width: 240px; font-family: var(--font-body, inherit);">
          <h4 style="color:#2f7a4f; margin-bottom:0.25rem;">🏠 ${escapeHtml(r.organization_name)}</h4>
          <div style="margin-bottom: 0.35rem; display:flex; gap:0.4rem; align-items:center; flex-wrap:wrap;">
            <span class="badge badge--secondary" style="font-size:0.75rem;">User Type: Receiver / Orphanage</span>
            ${statusBadge}
          </div>
          ${stateLine}
          <p style="margin:0.2rem 0;"><strong>📍 Location:</strong> ${escapeHtml(address)}</p>
          ${userDist}
          ${r.description ? `<p class="text-muted" style="margin:0.2rem 0;"><em>"${escapeHtml(r.description)}"</em></p>` : ''}
          <div class="popup-contact" style="margin-top:0.4rem;">
            ${phone ? `<div>📞 <strong>Phone:</strong> <a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a></div>` : ''}
            ${email ? `<div>✉️ <strong>Email:</strong> <a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></div>` : ''}
          </div>
          <div class="popup-actions" style="margin-top:0.5rem; display:flex; gap:0.5rem;">
            <a href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}" target="_blank" class="btn btn--secondary btn--small">Get Directions</a>
            ${Auth.isLoggedIn() && Auth.getUser().role === 'provider' ? `<a href="/listings/new" class="btn btn--primary btn--small">Donate Food</a>` : ''}
          </div>
        </div>
      `;

      const marker = L.marker([lat, lng], { icon: orphanageIcon });
      marker.bindPopup(popupContent);
      orphanageLayer.addLayer(marker);
    });
  }

  function renderProviders(filterText = '') {
    providerLayer.clearLayers();
    const query = filterText.toLowerCase();

    const filtered = allProviders.filter((p) => {
      const coords = getEffectiveCoords(p);
      if (!coords) return false;
      if (!query) return true;
      const haystack = `${p.organization_name} ${p.city} ${p.state || ''} ${p.address} ${p.pincode || ''} ${p.description}`.toLowerCase();
      return haystack.includes(query);
    });

    providerCountEl.textContent = filtered.length;

    filtered.forEach((p) => {
      const coords = getEffectiveCoords(p);
      if (!coords) return;
      const { lat, lng } = coords;

      const phone = p.phone || p.contact_info;
      const email = p.email;
      const locParts = [p.address, p.city, p.state, p.pincode].filter(Boolean);
      const address = locParts.length > 0 ? locParts.join(', ') : 'Address on file';
      const activeDonations = p.active_donations_count != null ? p.active_donations_count : 0;
      const stateLine = p.state
        ? `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> ${escapeHtml(p.state)}</p>`
        : `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> Not specified</p>`;

      const userDist = userLocation
        ? `<p style="color:#2563eb; font-weight:500;">📏 ${haversineDistanceKm(userLocation.lat, userLocation.lng, lat, lng).toFixed(2)} km from you</p>`
        : '';

      const popupContent = `
        <div style="min-width: 240px; font-family: var(--font-body, inherit);">
          <h4 style="color:#2563eb; margin-bottom:0.25rem;">🏬 ${escapeHtml(p.organization_name)}</h4>
          <div style="margin-bottom: 0.35rem; display:flex; gap:0.4rem; align-items:center; flex-wrap:wrap;">
            <span class="badge badge--secondary" style="font-size:0.75rem;">User Type: Food Provider</span>
            <span class="badge badge--available" style="font-size:0.75rem;">${activeDonations} active donation${activeDonations === 1 ? '' : 's'}</span>
          </div>
          ${stateLine}
          <p style="margin:0.2rem 0;"><strong>📍 Location:</strong> ${escapeHtml(address)}</p>
          ${userDist}
          ${p.description ? `<p class="text-muted" style="margin:0.2rem 0;"><em>"${escapeHtml(p.description)}"</em></p>` : ''}
          <div class="popup-contact" style="margin-top:0.4rem;">
            ${phone ? `<div>📞 <strong>Phone:</strong> <a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a></div>` : ''}
            ${email ? `<div>✉️ <strong>Email:</strong> <a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></div>` : ''}
          </div>
          <div class="popup-actions" style="margin-top:0.5rem; display:flex; gap:0.5rem;">
            <a href="/listings?search=${encodeURIComponent(p.organization_name)}" class="btn btn--primary btn--small">View Donations</a>
            <a href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}" target="_blank" class="btn btn--secondary btn--small">Directions</a>
          </div>
        </div>
      `;

      const marker = L.marker([lat, lng], { icon: providerIcon });
      marker.bindPopup(popupContent);
      providerLayer.addLayer(marker);
    });
  }

  function renderListings(filterText = '') {
    listingsLayer.clearLayers();
    const query = filterText.toLowerCase();

    // REQUIREMENT 1 & 8: Filter out Completed or Cancelled donations
    const activeStatuses = new Set(['available', 'reserved', 'pickup_pending', 'scheduled']);

    const filtered = allListings.filter((item) => {
      const coords = getEffectiveCoords(item);
      if (!coords) return false;
      const status = (item.status || '').toLowerCase();
      if (!activeStatuses.has(status)) return false; // Exclude completed / collected / cancelled / expired
      if (!query) return true;
      const providerName = item.provider ? item.provider.organization_name : '';
      const providerState = (item.provider && item.provider.state) ? item.provider.state : '';
      const haystack = `${item.food_name} ${providerName} ${providerState} ${item.pickup_location} ${item.description}`.toLowerCase();
      return haystack.includes(query);
    });

    listingsCountEl.textContent = filtered.length;

    filtered.forEach((item) => {
      const coords = getEffectiveCoords(item);
      if (!coords) return;
      const { lat, lng } = coords;

      const statusVal = (item.status || 'available').replace('_', ' ');
      const statusBadge = `<span class="badge badge--available" style="font-size:0.75rem;">${escapeHtml(statusVal.toUpperCase())}</span>`;
      const providerName = item.provider ? item.provider.organization_name : 'Food Provider';
      const providerState = (item.provider && item.provider.state) ? item.provider.state : '';
      const stateLine = providerState ? `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> ${escapeHtml(providerState)}</p>` : '';

      const scheduleLine = item.pickup_start_time
        ? `<p style="margin-top:0.25rem; font-size:0.83rem; color:#4b5563;">⏰ Collection: <strong>${escapeHtml(formatDateTime(item.pickup_start_time))}</strong></p>`
        : '';

      const popupContent = `
        <div style="min-width: 240px; font-family: var(--font-body, inherit);">
          <h4 style="color:#d97706; margin-bottom:0.25rem;">🍲 ${escapeHtml(item.food_name)}</h4>
          <div style="display:flex; gap:0.4rem; align-items:center; margin-bottom:0.35rem;">
            ${statusBadge}
            <span style="font-size:0.82rem; font-weight:600; color:#374151;">📦 ${escapeHtml(item.quantity)} ${escapeHtml(item.quantity_unit)}</span>
          </div>
          <p style="margin:0.2rem 0;"><strong>🏬 Provider:</strong> ${escapeHtml(providerName)}</p>
          ${stateLine}
          <p style="margin:0.2rem 0;"><strong>📍 Location:</strong> ${escapeHtml(item.pickup_location)}</p>
          ${scheduleLine}
          <div class="popup-actions" style="margin-top: 0.5rem; display:flex; gap:0.5rem;">
            <a href="/listings/${item.id}" class="btn btn--primary btn--small">View & Request</a>
            <a href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}" target="_blank" class="btn btn--secondary btn--small">Directions</a>
          </div>
        </div>
      `;

      const marker = L.marker([lat, lng], { icon: donationIcon });
      marker.bindPopup(popupContent);
      listingsLayer.addLayer(marker);
    });
  }

  // REQUIREMENT 3 & 4: View Route / View Map for a scheduled pickup
  async function loadRouteForPickup(pickupId) {
    loadingEl.hidden = false;
    alertEl.innerHTML = '';

    try {
      const res = await Api.get(`/api/pickups/${pickupId}`);
      const pickup = res.data;
      loadingEl.hidden = true;

      // REQUIREMENT 1 & 8: If completed or cancelled, do not display active route on map
      if (pickup.status === 'completed' || pickup.status === 'cancelled' || pickup.status === 'failed') {
        showAlert(`Pickup #${pickupId} has status "${pickup.status.toUpperCase()}" and is no longer active on the map.`, 'info');
        return;
      }

      const p = pickup.provider || {};
      const r = pickup.recipient || {};
      const listing = pickup.listing || {};

      let pLat = parseFloat(p.latitude || listing.latitude);
      let pLng = parseFloat(p.longitude || listing.longitude);
      let rLat = parseFloat(r.latitude);
      let rLng = parseFloat(r.longitude);

      if (isNaN(pLat) || isNaN(pLng) || !isInIndia(pLat, pLng) || isNaN(rLat) || isNaN(rLng) || !isInIndia(rLat, rLng)) {
        showAlert("Cannot display route: One or both parties do not have a valid location saved in India.", "info");
        return;
      }

      const pName = p.organization_name || 'Food Provider';
      const rName = r.organization_name || 'Orphanage / Receiver';
      const pLocParts = [p.address, p.city, p.state, p.pincode].filter(Boolean);
      const pAddress = pLocParts.length > 0 ? pLocParts.join(', ') : (listing.pickup_location || 'Address on file');
      const rLocParts = [r.address, r.city, r.state, r.pincode].filter(Boolean);
      const rAddress = rLocParts.length > 0 ? rLocParts.join(', ') : 'Address on file';
      const pState = p.state ? `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> ${escapeHtml(p.state)}</p>` : '';
      const rState = r.state ? `<p style="margin:0.2rem 0;"><strong>🗺️ State:</strong> ${escapeHtml(r.state)}</p>` : '';

      routeLayer.clearLayers();

      const pMarker = L.marker([pLat, pLng], { icon: providerIcon })
        .bindPopup(`
          <div style="min-width:220px; font-family: var(--font-body, inherit);">
            <h4 style="color:#2563eb; margin-bottom:0.25rem;">📍 Provider Location</h4>
            <p><strong>Name:</strong> ${escapeHtml(pName)}</p>
            <p><strong>User Type:</strong> Food Provider</p>
            ${pState}
            <p><strong>Location:</strong> ${escapeHtml(pAddress)}</p>
            <p>🍲 <strong>Food:</strong> ${escapeHtml(listing.food_name || 'Surplus Food')}</p>
          </div>
        `);
      routeLayer.addLayer(pMarker);

      const rMarker = L.marker([rLat, rLng], { icon: orphanageIcon })
        .bindPopup(`
          <div style="min-width:220px; font-family: var(--font-body, inherit);">
            <h4 style="color:#2f7a4f; margin-bottom:0.25rem;">📍 Receiver / Orphanage</h4>
            <p><strong>Name:</strong> ${escapeHtml(rName)}</p>
            <p><strong>User Type:</strong> Orphanage / Receiver</p>
            ${rState}
            <p><strong>Location:</strong> ${escapeHtml(rAddress)}</p>
          </div>
        `);
      routeLayer.addLayer(rMarker);

      drawRoute(pLat, pLng, rLat, rLng, pName, rName);
      pMarker.openPopup();
    } catch (err) {
      loadingEl.hidden = true;
      showAlert(err.message || 'Could not load scheduled route details.');
    }
  }

  async function loadMapData() {
    loadingEl.hidden = false;
    alertEl.innerHTML = '';

    try {
      const [recipientsRes, providersRes, listingsRes] = await Promise.all([
        Api.get('/api/recipients?limit=100'),
        Api.get('/api/providers?limit=100'),
        Api.get('/api/listings?status=active&limit=100'),
      ]);

      loadingEl.hidden = true;

      allOrphanages = (recipientsRes.data && recipientsRes.data.recipients) || [];
      allProviders = (providersRes.data && providersRes.data.providers) || [];
      allListings = (listingsRes.data && listingsRes.data.listings) || [];

      renderOrphanages();
      renderProviders();
      renderListings();

      const pickupIdParam = urlParams.get('pickup_id');
      if (pickupIdParam) {
        await loadRouteForPickup(pickupIdParam);
      } else {
        // Fit map bounds to show all valid Indian locations
        const validPoints = [];
        allOrphanages.forEach((r) => {
          const coords = getEffectiveCoords(r);
          if (coords) validPoints.push([coords.lat, coords.lng]);
        });
        allProviders.forEach((p) => {
          const coords = getEffectiveCoords(p);
          if (coords) validPoints.push([coords.lat, coords.lng]);
        });
        allListings.forEach((l) => {
          if (l.status === 'available' || l.status === 'reserved' || l.status === 'pickup_pending') {
            const coords = getEffectiveCoords(l);
            if (coords) validPoints.push([coords.lat, coords.lng]);
          }
        });

        if (validPoints.length > 0 && !(urlParams.get('lat') && urlParams.get('lng'))) {
          map.fitBounds(validPoints, { padding: [40, 40], maxZoom: 13 });
        }
      }
    } catch (err) {
      loadingEl.hidden = true;
      showAlert(err.message || 'Could not load map data.');
    }
  }

  toggleOrphanages.addEventListener('change', () => {
    if (toggleOrphanages.checked) {
      map.addLayer(orphanageLayer);
    } else {
      map.removeLayer(orphanageLayer);
    }
  });

  if (toggleProviders) {
    toggleProviders.addEventListener('change', () => {
      if (toggleProviders.checked) {
        map.addLayer(providerLayer);
      } else {
        map.removeLayer(providerLayer);
      }
    });
  }

  toggleListings.addEventListener('change', () => {
    if (toggleListings.checked) {
      map.addLayer(listingsLayer);
    } else {
      map.removeLayer(listingsLayer);
    }
  });

  searchInput.addEventListener('input', () => {
    const val = searchInput.value.trim();
    renderOrphanages(val);
    renderProviders(val);
    renderListings(val);
  });

  locateMeBtn.addEventListener('click', () => {
    if (!navigator.geolocation) {
      showAlert('Geolocation is not supported by your browser. Centering on default India location.', 'info');
      map.setView([DEFAULT_INDIA_LAT, DEFAULT_INDIA_LNG], 10);
      return;
    }
    locateMeBtn.disabled = true;
    locateMeBtn.textContent = 'Locating…';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locateMeBtn.disabled = false;
        locateMeBtn.textContent = '📍 Near Me';
        const userLat = pos.coords.latitude;
        const userLng = pos.coords.longitude;

        if (!isInIndia(userLat, userLng)) {
          showAlert('Your current location is outside India. Centering on default India location for donation mapping.', 'info');
          map.setView([DEFAULT_INDIA_LAT, DEFAULT_INDIA_LNG], 10);
          return;
        }

        userLocation = { lat: userLat, lng: userLng };
        map.setView([userLat, userLng], 13);

        L.circleMarker([userLat, userLng], {
          radius: 8,
          fillColor: '#1d4ed8',
          color: '#ffffff',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.9,
        }).addTo(map).bindPopup('<strong>Your Current Location</strong>').openPopup();

        const searchVal = searchInput.value.trim();
        renderOrphanages(searchVal);
        renderProviders(searchVal);
      },
      (err) => {
        locateMeBtn.disabled = false;
        locateMeBtn.textContent = '📍 Near Me';

        let msg = 'Could not retrieve your location. Check browser location permissions.';
        if (err.code === err.PERMISSION_DENIED) {
          msg = 'Location access was denied in browser permissions. Centering map on default India location.';
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          msg = 'Location information is unavailable. Centering map on default India location.';
        } else if (err.code === err.TIMEOUT) {
          msg = 'Location request timed out. Centering map on default India location.';
        }

        showAlert(msg, 'info');
        map.setView([DEFAULT_INDIA_LAT, DEFAULT_INDIA_LNG], 10);
      },
      {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 60000,
      }
    );
  });

  // Initial load
  loadMapData();
})();
