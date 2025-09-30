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

import { GatewayClient, GatewayClientError } from '../src';
import { createHash, randomBytes } from 'crypto';

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

export class LightningOperations {
  private client: GatewayClient;
  private gatewayNpub: string;

  constructor(gatewayUrl: string) {
    this.client = new GatewayClient(gatewayUrl);
    this.gatewayNpub = 'npub1gateway...'; // Replace with actual gateway npub
  }

  /**
   * Create a 31510 intent for gBTC lift operation
   */
  createLiftIntent(amountSats: number, assetId: string = 'gBTC'): LightningIntent {
    return {
      actionId: `lift_${Date.now()}_${randomBytes(4).toString('hex')}`,
      type: 'lightning:lift',
      params: {
        assetId,
        amount: amountSats,
        feeAssetId: 'gBTC',
        feeAmount: 10 // 10 sats in gBTC
      },
      expiresAt: Math.floor(Date.now() / 1000) + 15 * 60 // 15 minutes
    };
  }

  /**
   * Create a 31510 intent for gBTC land operation
   */
  createLandIntent(
    amountSats: number,
    lightningInvoice: string,
    assetId: string = 'gBTC'
  ): LightningIntent {
    return {
      actionId: `land_${Date.now()}_${randomBytes(4).toString('hex')}`,
      type: 'lightning:land',
      params: {
        assetId,
        amount: amountSats,
        lightningInvoice,
        feeAssetId: 'gBTC',
        feeAmount: Math.floor(amountSats * 0.001) // 0.1% fee
      },
      expiresAt: Math.floor(Date.now() / 1000) + 15 * 60
    };
  }

  /**
   * Simulate 31500 Service Request for Lightning operations
   */
  async simulate31500ServiceRequest(
    action: string,
    assetId: string,
    amount: number
  ): Promise<ServiceRequest> {
    const request: ServiceRequest = {
      action,
      assetId,
      amount,
      timestamp: Math.floor(Date.now() / 1000)
    };

    console.log('\n📤 31500 Service Request:');
    console.log(JSON.stringify(request, null, 2));
    return request;
  }

  /**
   * Simulate 31501 Service Response from gateway
   */
  async simulate31501ServiceResponse(
    request: ServiceRequest,
    invoice?: string
  ): Promise<ServiceResponse> {
    const response: ServiceResponse = {
      status: 'pending',
      action: request.action,
      assetId: request.assetId,
      amount: request.amount,
      timestamp: Math.floor(Date.now() / 1000)
    };

    if (request.action === 'lift_lightning' && invoice) {
      response.invoice = invoice;
      response.expiresAt = Math.floor(Date.now() / 1000) + 3600; // 1 hour
    }

    console.log('\n📥 31501 Service Response:');
    console.log(JSON.stringify(response, null, 2));
    return response;
  }

  /**
   * Complete gBTC lift flow: Lightning → VTXO
   */
  async executeLiftFlow(
    amountSats: number,
    assetId: string = 'gBTC'
  ): Promise<SessionResult> {
    console.log(`\n🚀 Starting gBTC Lift Flow: ${amountSats} sats`);

    try {
      // Step 1: 31500 Service Request
      const serviceRequest = await this.simulate31500ServiceRequest(
        'lift_lightning',
        assetId,
        amountSats
      );

      // Step 2: Get Lightning invoice from gateway (simulated)
      const mockInvoice = `lnbc${amountSats}n1p3k8...`; // Mock invoice
      const serviceResponse = await this.simulate31501ServiceResponse(
        serviceRequest,
        mockInvoice
      );

      // Step 3: Create 31510 intent (after user pays Lightning invoice)
      const intent = this.createLiftIntent(amountSats, assetId);
      console.log('\n📋 31510 Intent (after Lightning payment):');
      console.log(JSON.stringify(intent, null, 2));

      // Step 4: Create session
      const sessionResp = await this.client.createSession({
        userPubkey: 'npub1user...', // Replace with actual user npub
        sessionType: 'lightning_lift',
        intentData: intent
      });
      const sessionId = sessionResp.sessionId;
      console.log(`\n✅ Session created: ${sessionId}`);

      // Step 5: Create challenge
      const challengeData = {
        payloadToSign: `0x${createHash('sha256')
          .update(JSON.stringify(intent, Object.keys(intent).sort()))
          .digest('hex')}`,
        type: 'sign_payload',
        payloadRef: `sha256:${createHash('sha256')
          .update(JSON.stringify(intent.params, Object.keys(intent.params).sort()))
          .digest('hex')}`
      };

      const context = {
        human: `Authorize gBTC lift of ${amountSats} sats via Lightning payment`,
        stepIndex: 1,
        stepTotal: 1
      };

      const challenge = await this.client.createChallenge(sessionId, {
        challengeData,
        context
      });
      console.log(`\n🔐 Challenge created: ${challenge.challengeId}`);

      // Step 6: Start ceremony (simulating user approval)
      const ceremonyResp = await this.client.startCeremony(sessionId);
      console.log(`\n🎭 Ceremony started: ${ceremonyResp.status}`);

      return {
        sessionId,
        intent,
        status: 'lift_initiated'
      };

    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw new Error(`Gateway Error: ${error.message}`);
      }
      throw error;
    }
  }

  /**
   * Complete gBTC land flow: VTXO → Lightning
   */
  async executeLandFlow(
    amountSats: number,
    lightningInvoice: string,
    assetId: string = 'gBTC'
  ): Promise<SessionResult> {
    console.log(`\n🛬 Starting gBTC Land Flow: ${amountSats} sats`);

    try {
      // Step 1: Create 31510 intent
      const intent = this.createLandIntent(amountSats, lightningInvoice, assetId);
      console.log('\n📋 31510 Intent:');
      console.log(JSON.stringify(intent, null, 2));

      // Step 2: Create session
      const sessionResp = await this.client.createSession({
        userPubkey: 'npub1user...', // Replace with actual user npub
        sessionType: 'lightning_land',
        intentData: intent
      });
      const sessionId = sessionResp.sessionId;
      console.log(`\n✅ Session created: ${sessionId}`);

      // Step 3: Create challenge for VTXO spending
      const challengeData = {
        payloadToSign: `0x${createHash('sha256')
          .update(JSON.stringify(intent, Object.keys(intent).sort()))
          .digest('hex')}`,
        type: 'sign_tx',
        payloadRef: `sha256:${createHash('sha256')
          .update(JSON.stringify(intent.params, Object.keys(intent.params).sort()))
          .digest('hex')}`
      };

      const context = {
        human: `Authorize gBTC land of ${amountSats} sats to Lightning invoice`,
        stepIndex: 1,
        stepTotal: 1
      };

      const challenge = await this.client.createChallenge(sessionId, {
        challengeData,
        context
      });
      console.log(`\n🔐 Challenge created: ${challenge.challengeId}`);

      // Step 4: Start ceremony
      const ceremonyResp = await this.client.startCeremony(sessionId);
      console.log(`\n🎭 Ceremony started: ${ceremonyResp.status}`);

      return {
        sessionId,
        intent,
        status: 'land_initiated'
      };

    } catch (error) {
      if (error instanceof GatewayClientError) {
        throw new Error(`Gateway Error: ${error.message}`);
      }
      throw error;
    }
  }

  /**
   * Monitor session status and print 31340/31341 events
   */
  async monitorSession(
    sessionId: string,
    timeout: number = 120000 // 2 minutes
  ): Promise<any> {
    console.log(`\n📊 Monitoring session: ${sessionId}`);

    const startTime = Date.now();

    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const status = await this.client.getCeremonyStatus(sessionId);
          console.log(`📈 Status: ${status.status} | Step: ${status.currentStep || 'N/A'}`);

          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(interval);

            console.log(`\n🎉 Session ${status.status}!`);

            // Simulate 31340/31341 event
            if (status.status === 'completed') {
              const event31340 = {
                status: 'success',
                refActionId: status.intentData?.actionId,
                results: {
                  txid: 'mock_txid_abc123...',
                  amountProcessed: status.intentData?.params?.amount,
                  feePaid: status.intentData?.params?.feeAmount
                },
                timestamp: Math.floor(Date.now() / 1000)
              };
              console.log('\n✅ 31340 Success Event:');
              console.log(JSON.stringify(event31340, null, 2));
            } else {
              const event31341 = {
                status: 'failure',
                code: status.errorCode || 1000,
                message: status.errorMessage || 'Unknown error',
                refActionId: status.intentData?.actionId,
                timestamp: Math.floor(Date.now() / 1000)
              };
              console.log('\n❌ 31341 Failure Event:');
              console.log(JSON.stringify(event31341, null, 2));
            }

            resolve(status);
          }

          if (Date.now() - startTime > timeout) {
            clearInterval(interval);
            reject(new Error('Timeout waiting for session completion'));
          }

        } catch (error) {
          clearInterval(interval);
          reject(error);
        }
      }, 5000); // Check every 5 seconds
    });
  }
}

// Example usage
export async function runLightningExamples() {
  const lightning = new LightningOperations('http://localhost:8000');

  try {
    // Execute lift flow
    const liftResult = await lightning.executeLiftFlow(100000, 'gBTC');
    console.log(`\n🎯 Lift flow initiated. Session ID: ${liftResult.sessionId}`);

    // Monitor lift completion
    const liftStatus = await lightning.monitorSession(liftResult.sessionId);
    console.log(`\n📊 Lift final status: ${liftStatus.status}`);

    // Execute land flow
    const landResult = await lightning.executeLandFlow(
      50000,
      'lnbc500000n1p3k8...',
      'gBTC'
    );
    console.log(`\n🎯 Land flow initiated. Session ID: ${landResult.sessionId}`);

    // Monitor land completion
    const landStatus = await lightning.monitorSession(landResult.sessionId);
    console.log(`\n📊 Land final status: ${landStatus.status}`);

  } catch (error) {
    console.error('❌ Error:', error);
  }
}