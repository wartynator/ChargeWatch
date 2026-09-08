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
    .index("by_checkedAt", ["checkedAt"])
    .index("by_stationId_and_checkedAt", ["stationId", "checkedAt"]),
});