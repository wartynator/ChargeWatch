import { v } from "convex/values";

import { internal } from "./_generated/api";
import {
  internalAction,
  internalMutation,
  query,
} from "./_generated/server";

const STATION_IDS = [73151, 72182] as const;
const API_URL = "https://zsedrive.sk/api/v4.7/stations";

const snapshotValidator = v.object({
  stationId: v.number(),
  connectorId: v.string(),
  evseId: v.string(),
  state: v.union(v.literal("available"), v.literal("unavailable")),
  rawState: v.string(),
  checkedAt: v.number(),
  name: v.string(),
  address: v.string(),
});

type Snapshot = {
  stationId: number;
  connectorId: string;
  evseId: string;
  state: "available" | "unavailable";
  rawState: string;
  checkedAt: number;
  name: string;
  address: string;
};

type ApiConnector = {
  id?: number | string;
  evseID?: number | string | null;
  state?: string;
};

type ApiStation = {
  id?: number;
  name?: string;
  address?: {
    street?: string | null;
    number?: string | null;
    city?: string | null;
    country?: string | null;
    zip?: string | null;
  };
  connectors?: ApiConnector[];
};

type ApiPayload = { station?: ApiStation };

function formatAddress(address: ApiStation["address"]): string {
  if (!address) return "";
  return [address.street, address.number, address.zip, address.city, address.country]
    .filter((part): part is string => Boolean(part))
    .join(", ");
}

function normalizeState(rawState: string): "available" | "unavailable" {
  return rawState.toUpperCase() === "AVAILABLE" ? "available" : "unavailable";
}

async function fetchStation(stationId: number): Promise<Snapshot[]> {
  const response = await fetch(`${API_URL}/${stationId}`, {
    headers: {
      Accept: "application/json",
      Referer: "https://zsedrive.sk/",
    },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`Station ${stationId} returned HTTP ${response.status}`);
  }

  const payload = (await response.json()) as ApiPayload;
  const station = payload.station;
  if (!station || !Array.isArray(station.connectors)) {
    throw new Error(`Station ${stationId} response has no connectors`);
  }

  const checkedAt = Date.now();
  return station.connectors.map((connector) => {
    const rawState = String(connector.state ?? "UNKNOWN").toUpperCase();
    return {
      stationId: station.id ?? stationId,
      connectorId: String(connector.id ?? ""),
      evseId: String(connector.evseID ?? ""),
      state: normalizeState(rawState),
      rawState,
      checkedAt,
      name: station.name ?? "",
      address: formatAddress(station.address),
    };
  });
}

export const collect = internalAction({
  args: {},
  handler: async (ctx): Promise<void> => {
    const results = await Promise.allSettled(STATION_IDS.map(fetchStation));
    const snapshots = results.flatMap((result, index) => {
      if (result.status === "fulfilled") return result.value;
      console.error(`Station ${STATION_IDS[index]} failed`, result.reason);
      return [];
    });

    if (snapshots.length === 0) {
      throw new Error("All station requests failed");
    }
    await ctx.runMutation(internal.stations.insertSnapshots, { snapshots });
  },
});

export const insertSnapshots = internalMutation({
  args: { snapshots: v.array(snapshotValidator) },
  handler: async (ctx, { snapshots }) => {
    await Promise.all(
      snapshots.map((snapshot) =>
        ctx.db.insert("connectorAvailability", snapshot),
      ),
    );
  },
});

export const latest = query({
  args: {},
  handler: async (ctx) => {
    const recent = await ctx.db
      .query("connectorAvailability")
      .withIndex("by_checked_at")
      .order("desc")
      .take(100);
    const seen = new Set<string>();
    return recent.filter((snapshot) => {
      const key = `${snapshot.stationId}:${snapshot.connectorId}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  },
});

export const history = query({
  args: {
    stationId: v.number(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, { stationId, limit }) =>
    ctx.db
      .query("connectorAvailability")
      .withIndex("by_station_checked_at", (queryBuilder) =>
        queryBuilder.eq("stationId", stationId),
      )
      .order("desc")
      .take(Math.min(Math.max(limit ?? 100, 1), 1000)),
});