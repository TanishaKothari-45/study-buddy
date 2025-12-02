"use client";

import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

interface AuthModalProps {
    isOpen: boolean;
    onClose: () => void;
}

type AuthMode = "login" | "signup";

export function AuthModal({ isOpen, onClose }: AuthModalProps) {
    const [mode, setMode] = useState<AuthMode>("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();

    const resetForm = () => {
        setEmail("");
        setPassword("");
        setFullName("");
        setError("");
    };

    const switchMode = (newMode: AuthMode) => {
        setMode(newMode);
        resetForm();
    };

    const handleClose = () => {
        resetForm();
        onClose();
    };

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            const response = await fetch("http://localhost:8001/auth/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ email, password }),
            });

            const data = await response.json();

            if (response.ok) {
                login(data.access_token);
                handleClose();
            } else {
                setError(data.detail || "Login failed");
            }
        } catch {
            setError("An error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleSignup = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            const response = await fetch("http://localhost:8001/auth/signup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ email, password, full_name: fullName }),
            });

            const data = await response.json();

            if (response.ok) {
                // After successful signup, switch to login mode
                setMode("login");
                resetForm();
                setError(""); // Clear any errors
            } else {
                setError(data.detail || "Signup failed");
            }
        } catch {
            setError("An error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-2xl font-bold text-center text-[hsl(var(--text))]">
                        {mode === "login" ? "Welcome Back" : "Create Account"}
                    </DialogTitle>
                    <DialogDescription className="text-center text-[hsl(var(--text-muted))]">
                        {mode === "login"
                            ? "Enter your credentials to access your account"
                            : "Enter your details to create a new account"}
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={mode === "login" ? handleLogin : handleSignup} className="space-y-4">
                    {error && (
                        <Alert variant="destructive">
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    {mode === "signup" && (
                        <div className="space-y-2">
                            <Label htmlFor="fullName" className="text-[hsl(var(--text))]">Full Name</Label>
                            <Input
                                id="fullName"
                                type="text"
                                placeholder="John Doe"
                                value={fullName}
                                onChange={(e) => setFullName(e.target.value)}
                            />
                        </div>
                    )}

                    <div className="space-y-2">
                        <Label htmlFor="email" className="text-[hsl(var(--text))]">Email</Label>
                        <Input
                            id="email"
                            type="email"
                            placeholder="m@example.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="password" className="text-[hsl(var(--text))]">Password</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                    </div>

                    <Button type="submit" className="w-full" disabled={loading}>
                        {loading
                            ? mode === "login"
                                ? "Logging in..."
                                : "Creating account..."
                            : mode === "login"
                                ? "Login"
                                : "Sign Up"}
                    </Button>
                </form>

                <div className="text-center text-sm text-[hsl(var(--text-muted))]">
                    {mode === "login" ? (
                        <>
                            Don&apos;t have an account?{" "}
                            <button
                                type="button"
                                onClick={() => switchMode("signup")}
                                className="text-[hsl(var(--accent))] hover:underline font-medium"
                            >
                                Sign up
                            </button>
                        </>
                    ) : (
                        <>
                            Already have an account?{" "}
                            <button
                                type="button"
                                onClick={() => switchMode("login")}
                                className="text-[hsl(var(--accent))] hover:underline font-medium"
                            >
                                Login
                            </button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
