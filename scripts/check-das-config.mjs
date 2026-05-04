#!/usr/bin/env node
import { dasRuntimePlan } from "../provisioner/src/daal.js";

const plan = dasRuntimePlan(process.env);

console.log(JSON.stringify(plan, null, 2));

if (!plan.ok) {
  process.exitCode = 1;
}
