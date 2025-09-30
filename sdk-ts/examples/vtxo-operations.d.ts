/**
 * VTXO Operations Examples for ArkRelay TypeScript SDK
 *
 * Demonstrates VTXO splitting, multi-VTXO transactions, and optimal change management
 *
 * Usage:
 * import { VtxoOperations } from './vtxo-operations';
 * const vtxoOps = new VtxoOperations('http://localhost:8000');
 *
 * // Split VTXO
 * const splitResult = await vtxoOps.executeSplitFlow('vtxo_123', [200000, 300000]);
 *
 * // Multi-VTXO transaction
 * const multiResult = await vtxoOps.executeMultiVtxoFlow('gUSD', 400000000, 'npub1recipient...');
 */
export interface VtxoIntent {
    actionId: string;
    type: string;
    params: Record<string, any>;
    expiresAt: number;
}
export interface VtxoInfo {
    vtxoId: string;
    amount: number;
    assetId: string;
    status: string;
}
export interface VtxoSelectionResult {
    selectedVtxoIds: string[];
    selectedVtxos: VtxoInfo[];
    totalInput: number;
    changeAmount: number;
}
export interface SessionResult {
    sessionId: string;
    intent: VtxoIntent;
    status: string;
    [key: string]: any;
}
export declare class VtxoOperations {
    private client;
    constructor(gatewayUrl: string);
    /**
     * Create a 31510 intent for VTXO splitting
     */
    createSplitIntent(vtxoId: string, splitAmounts: number[], assetId?: string, feeAssetId?: string): VtxoIntent;
    /**
     * Create a 31510 intent for multi-VTXO transaction
     */
    createMultiVtxoIntent(assetId: string, totalAmount: number, recipientPubkey: string, sourceVtxos?: string[], feeAssetId?: string): VtxoIntent;
    /**
     * Create a 31510 intent for optimal change management
     */
    createOptimalChangeIntent(assetId: string, amountNeeded: number, recipientPubkey: string, feeAssetId?: string): VtxoIntent;
    /**
     * Simulate getting user's available VTXOs
     */
    simulateVtxoInventory(userPubkey: string, assetId: string): Promise<VtxoInfo[]>;
    /**
     * Find optimal VTXO combination for given amount
     */
    findOptimalVtxoCombination(availableVtxos: VtxoInfo[], amountNeeded: number, strategy?: 'optimal' | 'greedy' | 'minimal'): string[];
    /**
     * Calculate optimal change amount
     */
    calculateChangeAmount(selectedVtxos: VtxoInfo[], amountNeeded: number, fees?: number): number;
    /**
     * Execute complete VTXO split flow
     */
    executeSplitFlow(vtxoId: string, splitAmounts: number[], assetId?: string): Promise<SessionResult>;
    /**
     * Execute multi-VTXO transaction flow
     */
    executeMultiVtxoFlow(assetId: string, totalAmount: number, recipientPubkey: string): Promise<SessionResult>;
    /**
     * Execute optimal change management flow
     */
    executeOptimalChangeFlow(assetId: string, amountNeeded: number, recipientPubkey: string): Promise<SessionResult>;
}
export declare function runVtxoExamples(): Promise<void>;
