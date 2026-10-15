import { ActionEngine } from '../../../_shared/runtime/ActionEngine';

export async function login(action: ActionEngine, username: string, password: string): Promise<void> {
    await action.navigate("/login");
    await action.enterText("username", username);
    await action.enterText("password", password);
    await action.click("login_button");
}

export async function addToCart(action: ActionEngine, productId: string): Promise<void> {
    await action.navigate("/products");
    await action.click("add_to_cart");
    await action.verifyText("flash", "{{notAParam}}");
}
