import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  connectorAvailability: defineTable({
    stationId: v.number(),
    connectorId: v.string(),
    evseId: v.string(),
    state: v.union(v.literal("available"), v.literal("unavailable")),
    rawState: v.string(),
    checkedAt: v.number(),
    name: v.string(),
    address: v.string(),
  })
    .index("by_checked_at", ["checkedAt"])
    .index("by_station_checked_at", ["stationId", "checkedAt"]),
});