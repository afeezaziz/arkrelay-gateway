/**
 * Lightning Operations Examples for ArkRelay TypeScript SDK
 *
 * Demonstrates complete gBTC lift/land operations with Nostr event flows
 *
 * Usage:
 * import { LightningOperations } from './lightning-operations';
 * const lightning = new LightningOperations('http://localhost:8000');
 *
 * // Lift flow
 * const liftResult = await lightning.executeLiftFlow(100000, 'gBTC');
 *
 * // Land flow
 * const landResult = await lightning.executeLandFlow(50000, 'lnbc...');
 */
export interface LightningIntent {
    actionId: string;
    type: string;
    params: {
        assetId: string;
        amount: number;
        feeAssetId: string;
        feeAmount: number;
    };
    expiresAt: number;
}
export interface SessionResult {
    sessionId: string;
    intent: LightningIntent;
    status: string;
}
export interface ServiceRequest {
    action: string;
    assetId: string;
    amount: number;
    timestamp: number;
}
export interface ServiceResponse {
    status: string;
    action: string;
    assetId: string;
    amount: number;
    timestamp: number;
    invoice?: string;
    expiresAt?: number;
}
export declare class LightningOperations {
    private client;
    private gatewayNpub;
    constructor(gatewayUrl: string);
    /**
     * Create a 31510 intent for gBTC lift operation
     */
    createLiftIntent(amountSats: number, assetId?: string): LightningIntent;
    /**
     * Create a 31510 intent for gBTC land operation
     */
    createLandIntent(amountSats: number, lightningInvoice: string, assetId?: string): LightningIntent;
    /**
     * Simulate 31500 Service Request for Lightning operations
     */
    simulate31500ServiceRequest(action: string, assetId: string, amount: number): Promise<ServiceRequest>;
    /**
     * Simulate 31501 Service Response from gateway
     */
    simulate31501ServiceResponse(request: ServiceRequest, invoice?: string): Promise<ServiceResponse>;
    /**
     * Complete gBTC lift flow: Lightning → VTXO
     */
    executeLiftFlow(amountSats: number, assetId?: string): Promise<SessionResult>;
    /**
     * Complete gBTC land flow: VTXO → Lightning
     */
    executeLandFlow(amountSats: number, lightningInvoice: string, assetId?: string): Promise<SessionResult>;
    /**
     * Monitor session status and print 31340/31341 events
     */
    monitorSession(sessionId: string, timeout?: number): Promise<any>;
}
export declare function runLightningExamples(): Promise<void>;
