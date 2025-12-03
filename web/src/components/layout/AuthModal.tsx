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

type AuthMode = "login" | "signup" | "forgot-password" | "reset-password";

export function AuthModal({ isOpen, onClose }: AuthModalProps) {
    const [mode, setMode] = useState<AuthMode>("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();

    const resetForm = () => {
        setEmail("");
        setPassword("");
        setFullName("");
        setNewPassword("");
        setConfirmPassword("");
        setError("");
        setSuccessMessage("");
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

    const handleForgotPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            const response = await fetch("http://localhost:8001/auth/forgot-password", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ email }),
            });

            const data = await response.json();

            if (response.ok) {
                setMode("reset-password");
            } else {
                setError(data.detail || "Email not found");
            }
        } catch {
            setError("An error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleResetPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");

        if (newPassword !== confirmPassword) {
            setError("Passwords do not match");
            return;
        }

        if (newPassword.length < 6) {
            setError("Password must be at least 6 characters");
            return;
        }

        setLoading(true);

        try {
            const response = await fetch("http://localhost:8001/auth/reset-password", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ email, new_password: newPassword }),
            });

            const data = await response.json();

            if (response.ok) {
                setSuccessMessage("Password reset successfully!");
                setMode("login");
                resetForm();
            } else {
                setError(data.detail || "Failed to reset password");
            }
        } catch {
            setError("An error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const getFormHandler = () => {
        switch (mode) {
            case "login":
                return handleLogin;
            case "signup":
                return handleSignup;
            case "forgot-password":
                return handleForgotPassword;
            case "reset-password":
                return handleResetPassword;
        }
    };

    const getTitle = () => {
        switch (mode) {
            case "login":
                return "Welcome Back";
            case "signup":
                return "Create Account";
            case "forgot-password":
                return "Forgot Password";
            case "reset-password":
                return "Reset Password";
        }
    };

    const getDescription = () => {
        switch (mode) {
            case "login":
                return "Enter your credentials to access your account";
            case "signup":
                return "Enter your details to create a new account";
            case "forgot-password":
                return "Enter your email to reset your password";
            case "reset-password":
                return `Enter your new password for ${email}`;
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-2xl font-bold text-center text-[hsl(var(--text))]">
                        {getTitle()}
                    </DialogTitle>
                    <DialogDescription className="text-center text-[hsl(var(--text-muted))]">
                        {getDescription()}
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={getFormHandler()} className="space-y-4">
                    {error && (
                        <Alert variant="destructive">
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    {successMessage && (
                        <Alert>
                            <AlertDescription className="text-green-600">{successMessage}</AlertDescription>
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

                    {(mode === "login" || mode === "signup" || mode === "forgot-password") && (
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
                    )}

                    {(mode === "login" || mode === "signup") && (
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
                    )}

                    {mode === "reset-password" && (
                        <>
                            <div className="space-y-2">
                                <Label htmlFor="newPassword" className="text-[hsl(var(--text))]">New Password</Label>
                                <Input
                                    id="newPassword"
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="confirmPassword" className="text-[hsl(var(--text))]">Confirm Password</Label>
                                <Input
                                    id="confirmPassword"
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    required
                                />
                            </div>
                        </>
                    )}

                    {mode === "login" && (
                        <div className="flex justify-end">
                            <button
                                type="button"
                                onClick={() => switchMode("forgot-password")}
                                className="text-sm text-[hsl(var(--text-muted))] hover:text-[hsl(var(--accent))] hover:underline"
                            >
                                Forgot password?
                            </button>
                        </div>
                    )}

                    <Button type="submit" className="w-full" disabled={loading}>
                        {loading
                            ? mode === "login"
                                ? "Logging in..."
                                : mode === "signup"
                                    ? "Creating account..."
                                    : mode === "forgot-password"
                                        ? "Verifying..."
                                        : "Resetting..."
                            : mode === "login"
                                ? "Login"
                                : mode === "signup"
                                    ? "Sign Up"
                                    : mode === "forgot-password"
                                        ? "Continue"
                                        : "Reset Password"}
                    </Button>
                </form>

                <div className="text-center text-sm text-[hsl(var(--text-muted))]">
                    {mode === "login" && (
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
                    )}
                    {mode === "signup" && (
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
                    {(mode === "forgot-password" || mode === "reset-password") && (
                        <button
                            type="button"
                            onClick={() => switchMode("login")}
                            className="text-[hsl(var(--accent))] hover:underline font-medium"
                        >
                            ← Back to Login
                        </button>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
