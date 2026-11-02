#!/usr/bin/env node
/**
 * OCR scanned CSC PDF pages into a private text artifact.
 * Requires poppler-utils and Tesseract installed by the workflow.
 */
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
    ...options
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} failed: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return result.stdout || "";
}

async function main() {
  const outputDir = process.env.OUTPUT_DIR || "private-extraction";
  const reportPath = path.join(outputDir, "extraction-report.json");
  const report = JSON.parse(await readFile(reportPath, "utf8"));
  const pdfPath = report.pdf_file;
  if (!pdfPath) throw new Error("Extraction report does not identify the downloaded PDF.");

  const tempDir = await mkdtemp(path.join(os.tmpdir(), "csc-ocr-"));
  try {
    const prefix = path.join(tempDir, "page");
    run("pdftoppm", ["-r", "200", "-jpeg", "-jpegopt", "quality=88", pdfPath, prefix]);
    const images = (await readdir(tempDir))
      .filter((name) => /^page-\d+\.jpg$/i.test(name))
      .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]));
    if (images.length !== report.page_count) {
      throw new Error(`Rendered ${images.length} pages but PDF.js reported ${report.page_count}.`);
    }

    const pageTexts = [];
    let totalCharacters = 0;
    for (let index = 0; index < images.length; index += 1) {
      const imagePath = path.join(tempDir, images[index]);
      const text = run("tesseract", [imagePath, "stdout", "-l", "eng", "--psm", "6"]).trim();
      pageTexts.push(`===== PAGE ${index + 1} =====\n${text}`);
      totalCharacters += text.length;
    }

    const ocrPath = path.join(outputDir, `${report.source_id}-${report.drive_file_id}-ocr.txt`);
    await writeFile(ocrPath, pageTexts.join("\n\n") + "\n", "utf8");
    report.ocr_performed = true;
    report.ocr_engine = "tesseract";
    report.ocr_language = "eng";
    report.ocr_page_count = images.length;
    report.ocr_extracted_characters = totalCharacters;
    report.ocr_text_file = ocrPath;
    report.status = totalCharacters > 0 ? "ocr_text_extracted_private_review_required" : "ocr_completed_no_text_detected";
    await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");

    console.log(JSON.stringify({
      status: report.status,
      source_id: report.source_id,
      drive_file_id: report.drive_file_id,
      pdf_bytes: report.pdf_bytes,
      page_count: report.page_count,
      ocr_page_count: images.length,
      ocr_extracted_characters: totalCharacters,
      ocr_text_file: ocrPath,
      published: false
    }, null, 2));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(`OCR stopped safely: ${error.message || error}`);
  process.exitCode = 1;
});
