import type { ErrorCode } from "@contracts/ts/dso-contracts";

/** Mirrors contracts ErrorResponse: { error: { code, message, details } }. */
export class ApiError extends Error {
  constructor(
    public code: ErrorCode | "network_error",
    message: string,
    public status: number,
    public details: unknown = null,
  ) {
    super(message);
  }
}
