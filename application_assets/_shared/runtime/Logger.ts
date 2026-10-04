export class Logger {
    private static getTimestamp(): string {
        return new Date().toISOString();
    }

    static info(message: string): void {
        console.log(`[INFO] [${this.getTimestamp()}] ${message}`);
    }

    static warn(message: string): void {
        console.warn(`[WARN] [${this.getTimestamp()}] ${message}`);
    }

    static error(message: string): void {
        console.error(`[ERROR] [${this.getTimestamp()}] ${message}`);
    }

    static step(action: string, locator?: string, value?: string): void {
        console.log('\n--------------------------------');
        console.log(`[STEP] ${action}`);
        if (locator) { console.log(`Locator : ${locator}`); }
        if (value) { console.log(`Value    : ${value}`); }
        console.log('--------------------------------\n');
    }

    static success(message: string): void {
        console.log(`[SUCCESS] [${this.getTimestamp()}] ${message}`);
    }
}
