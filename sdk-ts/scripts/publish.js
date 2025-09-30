#!/usr/bin/env node

/**
 * Publish ArkRelay TypeScript SDK to NPM
 *
 * Usage:
 *   node scripts/publish.js --test    # Dry run
 *   node scripts/publish.js           # Actual publish
 *   node scripts/publish.js --version 0.2.0  # Bump version
 */

import { execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function runCommand(cmd, description) {
  console.log(`\n🔄 ${description}`);
  console.log(`Running: ${cmd}`);

  try {
    const output = execSync(cmd, { encoding: 'utf8', stdio: 'pipe' });
    console.log(`✅ ${description} completed successfully`);
    if (output) {
      console.log(`Output: ${output}`);
    }
    return output;
  } catch (error) {
    console.error(`❌ Error: ${error.message}`);
    console.error(`❌ Command failed: ${cmd}`);
    process.exit(1);
  }
}

function bumpVersion(newVersion) {
  const packageJsonPath = join(process.cwd(), 'package.json');
  const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8'));

  packageJson.version = newVersion;

  writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');
  console.log(`📦 Version bumped to ${newVersion}`);
}

function main() {
  const args = process.argv.slice(2);
  const testMode = args.includes('--test');
  const versionArg = args.find(arg => arg.startsWith('--version'));

  // Bump version if specified
  if (versionArg) {
    const newVersion = versionArg.split('=')[1] || args[args.indexOf('--version') + 1];
    if (newVersion) {
      bumpVersion(newVersion);
    }
  }

  // Validate we're in the right directory
  if (!require('fs').existsSync('package.json')) {
    console.error('❌ Error: package.json not found. Run from sdk-ts directory.');
    process.exit(1);
  }

  const packageJson = JSON.parse(readFileSync('package.json', 'utf8'));
  const version = packageJson.version;

  console.log(`🚀 Publishing ArkRelay TypeScript SDK v${version}`);

  if (testMode) {
    console.log('🧪 Test mode - no actual publish');
  }

  // Clean previous builds
  runCommand('npm run clean', 'Cleaning previous builds');

  // Install dependencies
  runCommand('npm install', 'Installing dependencies');

  // Build the package
  runCommand('npm run build', 'Building package');

  // Run dry run to check
  runCommand('npm run publish:dry', 'Running dry run');

  // Check build output
  const distFiles = require('fs').readdirSync('dist');
  console.log(`📦 Built files: ${distFiles.join(', ')}`);

  // Publish to appropriate registry
  if (testMode) {
    console.log('\n🧪 Test publish skipped (use --publish to actually publish)');
    console.log('✅ Package is ready for publishing!');
  } else {
    runCommand('npm publish --access public', 'Publishing to NPM');
    console.log('\n🎉 Published to NPM!');
    console.log('Install with: npm install arkrelay-sdk');
  }

  // Show package contents
  console.log('\n📋 Package contents:');
  runCommand('npm pack --json', 'Showing package contents');
}

main();