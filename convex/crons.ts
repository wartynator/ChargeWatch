import { cronJobs } from "convex/server";

import { internal } from "./_generated/api";

const crons = cronJobs();

crons.interval(
  "collect ZSE connector availability",
  { minutes: 1 },
  internal.stations.collect,
);

export default crons;