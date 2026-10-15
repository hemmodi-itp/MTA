import * as fs from 'fs';
import { describe, expect, it } from 'vitest';
import { sizeFromName, synthesizeUpload } from './ActionEngine';

describe('upload fixtures named by generated test data', () => {
  it('reads a size from the name', () => {
    expect(sizeFromName('large_dataset_5mb.csv')).toBe(5 * 1024 * 1024);
    expect(sizeFromName('img_200KB.png')).toBe(200 * 1024);
    expect(sizeFromName('sample_data.csv')).toBeUndefined();
    expect(sizeFromName('huge_9gb.bin')).toBe(20 * 1024 * 1024);              // capped
  });

  it('writes a file with the requested name, type-appropriate content and size', () => {
    const csv = synthesizeUpload('sample_data.csv');
    expect(csv.endsWith('sample_data.csv')).toBe(true);
    expect(fs.readFileSync(csv, 'utf8').startsWith('name,value\n')).toBe(true);
    expect(fs.statSync(csv).size).toBe(512);
    const big = synthesizeUpload('large_dataset_2mb.csv');
    expect(fs.statSync(big).size).toBe(2 * 1024 * 1024);
    const png = fs.readFileSync(synthesizeUpload('photo.png'));
    expect(png.subarray(1, 4).toString()).toBe('PNG');
    expect(fs.statSync(synthesizeUpload('malicious_installer.exe')).size).toBe(512);
  });
});
