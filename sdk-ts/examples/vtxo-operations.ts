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

import { GatewayClient, GatewayClientError } from '../src';
import { createHash, randomBytes } from 'crypto';

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

export class VtxoOperations {
  private client: GatewayClient;

  constructor(gatewayUrl: string) {
    this.client = new GatewayClient(gatewayUrl);
  }

  /**
   * Create a 31510 intent for VTXO splitting
   */
  createSplitIntent(
    vtxoId: string,
    splitAmounts: number[],
    assetId: string = 'gBTC',
    feeAssetId: string = 'gBTC'
  ): VtxoIntent {
    return {
      actionId: `split_${Date.now()}_${randomBytes(4).toString('hex')}`,
      type: 'vtxo:split',
      params: {
        vtxoId,
        splitAmounts,
        assetId,
        feeAssetId,
        feeAmount: 10, // 10 sats in gBTC
        minChange: 1000 // Minimum change threshold
      },
      expiresAt: Math.floor(Date.now() / 1000) + 15 * 60
    };
  }

  /**
   * Create a 31510 intent for multi-VTXO transaction
   */
  createMultiVtxoIntent(
    assetId: string,
    totalAmount: number,
    recipientPubkey: string,
    sourceVtxos: string[] = [],
    feeAssetId: string = 'gBTC'
  ): VtxoIntent {
    return {
      actionId: `multi_${Date.now()}_${randomBytes(4).toString('hex')}`,
      type: 'vtxo:multi_transfer',
      params: {
        assetId,
        totalAmount,
        recipientPubkey,
        sourceVtxos,
        feeAssetId,
        feeAmount: 10,
        minChange: 1000,
        maxInputs: 5, // Maximum VTXOs to combine
        strategy: 'optimal' // optimal, greedy, minimal
      },
      expiresAt: Math.floor(Date.now() / 1000) + 15 * 60
    };
  }

  /**
   * Create a 31510 intent for optimal change management
   */
  createOptimalChangeIntent(
    assetId: string,
    amountNeeded: number,
    recipientPubkey: string,
    feeAssetId: string = 'gBTC'
  ): VtxoIntent {
    return {
      actionId: `change_${Date.now()}_${randomBytes(4).toString('hex')}`,
      type: 'vtxo:optimal_change',
      params: {
        assetId,
        amountNeeded,
        recipientPubkey,
        feeAssetId,
        feeAmount: 10,
        changeThreshold: 5000, // Minimum change amount to create
        dustLimit: 1, // 1 satoshi dust limit for VTXOs
        preferExistingChange: true // Prefer using existing change VTXOs
      },
      expiresAt: Math.floor(Date.now() / 1000) + 15 * 60
    };
  }

  /**
   * Simulate getting user's available VTXOs
   */
  async simulateVtxoInventory(userPubkey: string, assetId: string): Promise<VtxoInfo[]> {
    // In real implementation, this would call the gateway
    return [
      { vtxoId: 'vtxo_large_1', amount: 500000000, assetId, status: 'available' },
      { vtxoId: 'vtxo_medium_1', amount: 100000000, assetId, status: 'available' },
      { vtxoId: 'vtxo_small_1', amount: 50000000, assetId, status: 'available' },
      { vtxoId: 'vtxo_change_1', amount: 12345, assetId, status: 'available' },
    ];
  }

  /**
   * Find optimal VTXO combination for given amount
   */
  findOptimalVtxoCombination(
    availableVtxos: VtxoInfo[],
    amountNeeded: number,
    strategy: 'optimal' | 'greedy' | 'minimal' = 'optimal'
  ): string[] {
    const availableAmounts = availableVtxos.map(vtxo => ({
      vtxoId: vtxo.vtxoId,
      amount: vtxo.amount
    }));

    // Sort based on strategy
    if (strategy === 'greedy') {
      availableAmounts.sort((a, b) => b.amount - a.amount);
    } else if (strategy === 'minimal') {
      availableAmounts.sort((a, b) => b.amount - a.amount);
    } else { // optimal
      availableAmounts.sort((a, b) => b.amount - a.amount);
    }

    const selected: string[] = [];
    let total = 0;

    for (const { vtxoId, amount } of availableAmounts) {
      if (total >= amountNeeded) {
        break;
      }
      selected.push(vtxoId);
      total += amount;
    }

    if (total < amountNeeded) {
      throw new Error(`Insufficient VTXO balance. Need: ${amountNeeded}, Available: ${total}`);
    }

    return selected;
  }

  /**
   * Calculate optimal change amount
   */
  calculateChangeAmount(
    selectedVtxos: VtxoInfo[],
    amountNeeded: number,
    fees: number = 10
  ): number {
    const totalInput = selectedVtxos.reduce((sum, vtxo) => sum + vtxo.amount, 0);
    const change = totalInput - amountNeeded - fees;

    // Only create change if above threshold
    const changeThreshold = 5000;
    return Math.max(0, change >= changeThreshold ? change : 0);
  }

  /**
   * Execute complete VTXO split flow
   */
  async executeSplitFlow(
    vtxoId: string,
    splitAmounts: number[],
    assetId: string = 'gBTC'
  ): Promise<SessionResult> {
    const totalSplit = splitAmounts.reduce((sum, amount) => sum + amount, 0);
    console.log(`\n✂️ Starting VTXO Split Flow: ${vtxoId} → [${splitAmounts.join(', ')}] (total: ${totalSplit})`);

    try {
      // Step 1: Create split intent
      const intent = this.createSplitIntent(vtxoId, splitAmounts, assetId);
      console.log('\n📋 31510 Split Intent:');
      console.log(JSON.stringify(intent, null, 2));

      // Step 2: Create session
      const sessionResp = await this.client.createSession({
        userPubkey: 'npub1user...',
        sessionType: 'vtxo_split',
        intentData: intent
      });
      const sessionId = sessionResp.sessionId;
      console.log(`\n✅ Session created: ${sessionId}`);

      // Step 3: Create multi-step challenge for split authorization
      for (let i = 0; i < splitAmounts.length; i++) {
        const amount = splitAmounts[i];
        const stepData = {
          stepIndex: i + 1,
          stepTotal: splitAmounts.length,
          splitAmount: amount,
          vtxoId
        };

        const challengeData = {
          payloadToSign: `0x${createHash('sha256')
            .update(JSON.stringify(stepData, Object.keys(stepData).sort()))
            .digest('hex')}`,
          type: 'sign_payload',
          payloadRef: `sha256:split_${i + 1}_${createHash('sha256')
            .update(amount.toString())
            .digest('hex')}`
        };

        const context = {
          human: `Step ${i + 1}/${splitAmounts.length}: Authorize split of ${amount} from ${vtxoId}`,
          splitDetails: stepData
        };

        const challenge = await this.client.createChallenge(sessionId, {
          challengeData,
          context
        });
        console.log(`\n🔐 Challenge ${i + 1}/${splitAmounts.length} created`);
      }

      // Step 4: Start ceremony
      const ceremonyResp = await this.client.startCeremony(sessionId);
      console.log(`\n🎭 Split ceremony started: ${ceremonyResp.status}`);

      return {
        sessionId,
        intent,
        splitAmounts,
        status: 'split_initiated'
      };

    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw new Error(`Gateway Error: ${error.message}`);
      }
      throw error;
    }
  }

  /**
   * Execute multi-VTXO transaction flow
   */
  async executeMultiVtxoFlow(
    assetId: string,
    totalAmount: number,
    recipientPubkey: string
  ): Promise<SessionResult> {
    console.log(`\n🔄 Starting Multi-VTXO Flow: ${totalAmount} ${assetId} → ${recipientPubkey}`);

    try {
      // Step 1: Get available VTXOs
      const availableVtxos = await this.simulateVtxoInventory('npub1user...', assetId);
      console.log('\n💰 Available VTXOs:');
      availableVtxos.forEach(vtxo => {
        console.log(`  - ${vtxo.vtxoId}: ${vtxo.amount} ${vtxo.assetId}`);
      });

      // Step 2: Find optimal combination
      const selectedVtxoIds = this.findOptimalVtxoCombination(availableVtxos, totalAmount);
      const selectedVtxos = availableVtxos.filter(vtxo => selectedVtxoIds.includes(vtxo.vtxoId));

      console.log('\n🎯 Selected VTXOs:');
      selectedVtxos.forEach(vtxo => {
        console.log(`  - ${vtxo.vtxoId}: ${vtxo.amount}`);
      });

      // Step 3: Calculate change
      const changeAmount = this.calculateChangeAmount(selectedVtxos, totalAmount);
      console.log(`\n💱 Change amount: ${changeAmount}`);

      // Step 4: Create intent
      const intent = this.createMultiVtxoIntent(
        assetId,
        totalAmount,
        recipientPubkey,
        selectedVtxoIds
      );

      // Add change information
      if (changeAmount > 0) {
        intent.params.changeAmount = changeAmount;
        intent.params.changeAddress = 'npub1user...'; // User's address for change
      }

      console.log('\n📋 31510 Multi-VTXO Intent:');
      console.log(JSON.stringify(intent, null, 2));

      // Step 5: Create session
      const sessionResp = await this.client.createSession({
        userPubkey: 'npub1user...',
        sessionType: 'multi_vtxo_transfer',
        intentData: intent
      });
      const sessionId = sessionResp.sessionId;
      console.log(`\n✅ Session created: ${sessionId}`);

      // Step 6: Create challenge
      const challengeData = {
        payloadToSign: `0x${createHash('sha256')
          .update(JSON.stringify(intent, Object.keys(intent).sort()))
          .digest('hex')}`,
        type: 'sign_tx',
        payloadRef: `sha256:multi_tx_${createHash('sha256')
          .update(JSON.stringify(intent.params, Object.keys(intent.params).sort()))
          .digest('hex')}`
      };

      const context = {
        human: `Authorize multi-VTXO transfer: ${totalAmount} ${assetId} to ${recipientPubkey.substring(0, 20)}...`,
        totalAmount,
        vtxoCount: selectedVtxos.length,
        changeAmount
      };

      const challenge = await this.client.createChallenge(sessionId, {
        challengeData,
        context
      });
      console.log(`\n🔐 Challenge created: ${challenge.challengeId}`);

      // Step 7: Start ceremony
      const ceremonyResp = await this.client.startCeremony(sessionId);
      console.log(`\n🎭 Multi-VTXO ceremony started: ${ceremonyResp.status}`);

      return {
        sessionId,
        intent,
        selectedVtxos,
        changeAmount,
        status: 'multi_vtxo_initiated'
      };

    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw new Error(`Gateway Error: ${error.message}`);
      }
      throw error;
    }
  }

  /**
   * Execute optimal change management flow
   */
  async executeOptimalChangeFlow(
    assetId: string,
    amountNeeded: number,
    recipientPubkey: string
  ): Promise<SessionResult> {
    console.log(`\n💱 Starting Optimal Change Flow: ${amountNeeded} ${assetId}`);

    try {
      // Step 1: Get available VTXOs including existing change
      const availableVtxos = await this.simulateVtxoInventory('npub1user...', assetId);

      // Check for existing change VTXOs that could be used
      const changeVtxos = availableVtxos.filter(vtxo => vtxo.vtxoId.includes('change'));
      const regularVtxos = availableVtxos.filter(vtxo => !vtxo.vtxoId.includes('change'));

      console.log('\n💰 Available VTXOs:');
      console.log(`  Regular: ${regularVtxos.length} VTXOs`);
      console.log(`  Change: ${changeVtxos.length} VTXOs`);

      // Step 2: Try to use existing change first
      let selectedVtxoIds: string[];
      let selectedVtxos: VtxoInfo[];

      try {
        // Try regular VTXOs first, then add change if needed
        const allVtxos = [...regularVtxos, ...changeVtxos];
        selectedVtxoIds = this.findOptimalVtxoCombination(allVtxos, amountNeeded, 'optimal');
        selectedVtxos = allVtxos.filter(vtxo => selectedVtxoIds.includes(vtxo.vtxoId));
      } catch (error) {
        // Insufficient balance
        throw error;
      }

      // Step 3: Calculate optimal change
      const fees = 10;
      const totalInput = selectedVtxos.reduce((sum, vtxo) => sum + vtxo.amount, 0);
      const changeAmount = totalInput - amountNeeded - fees;

      // Determine if change should be created
      const changeThreshold = 5000;
      const shouldCreateChange = changeAmount >= changeThreshold;

      console.log('\n📊 Change Analysis:');
      console.log(`  Total input: ${totalInput}`);
      console.log(`  Amount needed: ${amountNeeded}`);
      console.log(`  Fees: ${fees}`);
      console.log(`  Raw change: ${changeAmount}`);
      console.log(`  Create change: ${shouldCreateChange}`);

      // Step 4: Create intent
      const intent = this.createOptimalChangeIntent(assetId, amountNeeded, recipientPubkey);
      intent.params.selectedVtxos = selectedVtxoIds;
      intent.params.shouldCreateChange = shouldCreateChange;

      if (shouldCreateChange) {
        intent.params.changeAmount = changeAmount;
      }

      console.log('\n📋 31510 Optimal Change Intent:');
      console.log(JSON.stringify(intent, null, 2));

      // Step 5: Create session
      const sessionResp = await this.client.createSession({
        userPubkey: 'npub1user...',
        sessionType: 'optimal_change',
        intentData: intent
      });
      const sessionId = sessionResp.sessionId;
      console.log(`\n✅ Session created: ${sessionId}`);

      // Step 6: Create challenge
      const challengeData = {
        payloadToSign: `0x${createHash('sha256')
          .update(JSON.stringify(intent, Object.keys(intent).sort()))
          .digest('hex')}`,
        type: 'sign_tx',
        payloadRef: `sha256:optimal_change_${createHash('sha256')
          .update(JSON.stringify(intent.params, Object.keys(intent.params).sort()))
          .digest('hex')}`
      };

      const changeText = shouldCreateChange ? ` + ${changeAmount} change` : '';
      const context = {
        human: `Authorize optimal payment: ${amountNeeded} ${assetId}${changeText}`,
        inputVtxos: selectedVtxos.length,
        optimizeStrategy: 'use_existing_change_first'
      };

      const challenge = await this.client.createChallenge(sessionId, {
        challengeData,
        context
      });
      console.log(`\n🔐 Challenge created: ${challenge.challengeId}`);

      // Step 7: Start ceremony
      const ceremonyResp = await this.client.startCeremony(sessionId);
      console.log(`\n🎭 Optimal change ceremony started: ${ceremonyResp.status}`);

      return {
        sessionId,
        intent,
        selectedVtxos,
        changeAmount: shouldCreateChange ? changeAmount : 0,
        status: 'optimal_change_initiated'
      };

    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw new Error(`Gateway Error: ${error.message}`);
      }
      throw error;
    }
  }
}

// Example usage
export async function runVtxoExamples() {
  const vtxoOps = new VtxoOperations('http://localhost:8000');

  try {
    // Split VTXO
    const splitResult = await vtxoOps.executeSplitFlow(
      'vtxo_large_001',
      [200000, 300000],
      'gBTC'
    );
    console.log(`\n✂️ Split flow initiated. Session ID: ${splitResult.sessionId}`);

    // Multi-VTXO transaction
    const multiResult = await vtxoOps.executeMultiVtxoFlow(
      'gUSD',
      400000000,
      'npub1recipient...'
    );
    console.log(`\n🔄 Multi-VTXO flow initiated. Session ID: ${multiResult.sessionId}`);

    // Optimal change management
    const changeResult = await vtxoOps.executeOptimalChangeFlow(
      'gBTC',
      123456,
      'npub1recipient...'
    );
    console.log(`\n💱 Optimal change flow initiated. Session ID: ${changeResult.sessionId}`);

  } catch (error) {
    console.error('❌ Error:', error);
  }
}