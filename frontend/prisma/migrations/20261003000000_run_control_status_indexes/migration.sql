-- AlterEnum
ALTER TYPE "RunStatus" ADD VALUE 'cancelled';

-- AlterEnum
ALTER TYPE "TestStatus" ADD VALUE 'inconclusive';

-- DropIndex
DROP INDEX "Run_projectId_idx";

-- AlterTable
ALTER TABLE "Run" ADD COLUMN     "cancelRequested" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "heartbeatAt" TIMESTAMP(3);

-- CreateIndex
CREATE UNIQUE INDEX "Project_userId_githubUrl_key" ON "Project"("userId", "githubUrl");

-- CreateIndex
CREATE INDEX "Run_projectId_startedAt_idx" ON "Run"("projectId", "startedAt");

-- CreateIndex
CREATE INDEX "Run_status_startedAt_idx" ON "Run"("status", "startedAt");

-- CreateIndex
CREATE INDEX "RunEvent_createdAt_idx" ON "RunEvent"("createdAt");

-- CreateIndex
CREATE INDEX "RunStep_status_finishedAt_idx" ON "RunStep"("status", "finishedAt");

-- CreateIndex
CREATE INDEX "Session_expiresAt_idx" ON "Session"("expiresAt");
