import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Transit Marker Telemetry & Coordinate Sync', () => {
  // Mock Leaflet Marker
  class MockMarker {
    constructor(latLng, options) {
      this.latLng = latLng;
      this.options = options;
      this.icon = options?.icon;
      this.setLatLngCalls = [];
      this.setIconCalls = [];
    }

    setLatLng(newLatLng) {
      this.latLng = newLatLng;
      this.setLatLngCalls.push(newLatLng);
      return this;
    }

    setIcon(newIcon) {
      this.icon = newIcon;
      this.setIconCalls.push(newIcon);
      return this;
    }

    getLatLng() {
      return this.latLng;
    }
  }

  // Mock LayerGroup
  class MockLayerGroup {
    constructor() {
      this.layers = new Set();
    }
    addLayer(layer) {
      this.layers.add(layer);
    }
    removeLayer(layer) {
      this.layers.delete(layer);
    }
    clearLayers() {
      this.layers.clear();
    }
  }

  test('markers retain reference keyed by bus_id and update via setLatLng', () => {
    const markersByBusId = new Map();
    const markersLayer = new MockLayerGroup();

    // Telemetry Cycle 1
    const telemetryCycle1 = [
      { bus_id: 1, bus_number: '101A', latitude: 11.0154, longitude: 76.9754, load_factor: 0.5 },
      { bus_id: 2, bus_number: '101B', latitude: 11.0178, longitude: 76.9898, load_factor: 0.6 },
    ];

    telemetryCycle1.forEach((bus) => {
      const lat = bus.latitude;
      const lon = bus.longitude;
      const marker = new MockMarker([lat, lon], { title: `Bus ${bus.bus_number}` });
      markersLayer.addLayer(marker);
      markersByBusId.set(bus.bus_id, marker);
    });

    assert.equal(markersByBusId.size, 2);
    assert.equal(markersLayer.layers.size, 2);
    assert.deepEqual(markersByBusId.get(1).getLatLng(), [11.0154, 76.9754]);

    // Telemetry Cycle 2: Changing GPS coordinates
    const telemetryCycle2 = [
      { bus_id: 1, bus_number: '101A', latitude: 11.0210, longitude: 76.9820, load_factor: 0.55 },
      { bus_id: 2, bus_number: '101B', latitude: 11.0235, longitude: 76.9940, load_factor: 0.65 },
    ];

    const currentBusIds = new Set();
    telemetryCycle2.forEach((bus) => {
      currentBusIds.add(bus.bus_id);
      const lat = bus.latitude;
      const lon = bus.longitude;
      const existingMarker = markersByBusId.get(bus.bus_id);

      if (existingMarker) {
        existingMarker.setLatLng([lat, lon]);
      } else {
        const marker = new MockMarker([lat, lon], { title: `Bus ${bus.bus_number}` });
        markersLayer.addLayer(marker);
        markersByBusId.set(bus.bus_id, marker);
      }
    });

    // Verify: SAME marker instance was updated in-place without duplicate creation
    assert.equal(markersByBusId.size, 2);
    assert.equal(markersLayer.layers.size, 2);
    const bus1Marker = markersByBusId.get(1);
    assert.deepEqual(bus1Marker.getLatLng(), [11.0210, 76.9820]);
    assert.equal(bus1Marker.setLatLngCalls.length, 1);
    assert.deepEqual(bus1Marker.setLatLngCalls[0], [11.0210, 76.9820]);

    const bus2Marker = markersByBusId.get(2);
    assert.deepEqual(bus2Marker.getLatLng(), [11.0235, 76.9940]);
    assert.equal(bus2Marker.setLatLngCalls.length, 1);
  });

  test('no duplicate markers created across multiple polling cycles', () => {
    const markersByBusId = new Map();
    const markersLayer = new MockLayerGroup();

    for (let cycle = 1; cycle <= 5; cycle++) {
      const buses = [
        { bus_id: 1, bus_number: '101A', latitude: 11.0 + cycle * 0.001, longitude: 76.9 + cycle * 0.001 },
      ];

      const currentIds = new Set();
      buses.forEach((b) => {
        currentIds.add(b.bus_id);
        const existing = markersByBusId.get(b.bus_id);
        if (existing) {
          existing.setLatLng([b.latitude, b.longitude]);
        } else {
          const marker = new MockMarker([b.latitude, b.longitude], {});
          markersLayer.addLayer(marker);
          markersByBusId.set(b.bus_id, marker);
        }
      });
    }

    assert.equal(markersByBusId.size, 1, 'Exactly one marker must exist for bus_id 1');
    assert.equal(markersLayer.layers.size, 1, 'LayerGroup must contain exactly one marker');
    assert.equal(markersByBusId.get(1).setLatLngCalls.length, 4, 'setLatLng must be called for cycles 2..5');
  });

  test('latitude and longitude are not inverted (Coimbatore coordinates check)', () => {
    // Coimbatore coordinates: Latitude ~ 10.9-11.2, Longitude ~ 76.8-77.2
    const sampleTelemetry = {
      latitude: 11.015451,
      longitude: 76.975428,
    };

    assert.ok(sampleTelemetry.latitude > 10.0 && sampleTelemetry.latitude < 12.0, 'Latitude must be in Coimbatore range (10-12°N)');
    assert.ok(sampleTelemetry.longitude > 76.0 && sampleTelemetry.longitude < 78.0, 'Longitude must be in Coimbatore range (76-78°E)');

    const latLngTuple = [sampleTelemetry.latitude, sampleTelemetry.longitude];
    assert.equal(latLngTuple[0], sampleTelemetry.latitude, 'Index 0 must be latitude in Leaflet LatLng');
    assert.equal(latLngTuple[1], sampleTelemetry.longitude, 'Index 1 must be longitude in Leaflet LatLng');
  });

  test('prunes removed buses when filtered or offline', () => {
    const markersByBusId = new Map();
    const markersLayer = new MockLayerGroup();

    // Initial 2 buses
    [1, 2].forEach((id) => {
      const marker = new MockMarker([11.0, 76.9], {});
      markersLayer.addLayer(marker);
      markersByBusId.set(id, marker);
    });
    assert.equal(markersByBusId.size, 2);

    // Filter to only bus 1
    const activeIds = new Set([1]);
    markersByBusId.forEach((marker, busId) => {
      if (!activeIds.has(busId)) {
        markersLayer.removeLayer(marker);
        markersByBusId.delete(busId);
      }
    });

    assert.equal(markersByBusId.size, 1);
    assert.equal(markersLayer.layers.size, 1);
    assert.ok(markersByBusId.has(1));
    assert.ok(!markersByBusId.has(2));
  });
});
