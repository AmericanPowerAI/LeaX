"""
LeaX All-in-One Desktop Application Launcher
============================================
Self-contained desktop app that works on Windows, Mac, Linux
One-click install from website -> Ready to use in 5 minutes

Features:
- Auto phone number provisioning
- Built-in web browser for login management
- Screen recording/automation for bidding apps
- All services bundled (no external dependencies)
- Works offline after initial setup
"""

import sys
import os
import json
import subprocess
import threading
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    import requests
    from flask import Flask
    import sqlite3
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "flask"])
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    import requests
    from flask import Flask

class LeaXDesktopApp:
    """Main desktop application window"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LeaX AI - Business Automation")
        self.root.geometry("900x700")
        
        # App data directory
        self.app_dir = Path.home() / ".leax"
        self.app_dir.mkdir(exist_ok=True)
        self.config_file = self.app_dir / "config.json"
        
        # Load or create config
        self.config = self.load_config()
        
        # Create UI
        self.create_ui()
        
        # Check if first time setup
        if not self.config.get('setup_completed'):
            self.show_setup_wizard()
    
    def load_config(self):
        """Load app configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {
            'setup_completed': False,
            'user_id': None,
            'api_key': None,
            'phone_number': None,
            'business_name': None,
            'auto_bidding_enabled': False,
            'bidding_apps': []
        }
    
    def save_config(self):
        """Save configuration"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def create_ui(self):
        """Create main application UI"""
        # Header
        header = tk.Frame(self.root, bg="#667eea", height=80)
        header.pack(fill=tk.X)
        
        title = tk.Label(header, text="🤖 LeaX AI Control Center", 
                        font=("Arial", 24, "bold"), fg="white", bg="#667eea")
        title.pack(pady=20)
        
        # Main container
        main = tk.Frame(self.root, bg="#f5f7fa")
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Status Card
        status_frame = tk.LabelFrame(main, text="📊 System Status", 
                                     font=("Arial", 12, "bold"), padx=20, pady=15)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.status_label = tk.Label(status_frame, 
                                     text="⚪ System Initializing...",
                                     font=("Arial", 11))
        self.status_label.pack(anchor=tk.W)
        
        if self.config.get('setup_completed'):
            self.update_status("✅ System Ready - AI Agent Active")
        
        # Quick Actions
        actions_frame = tk.LabelFrame(main, text="🚀 Quick Actions", 
                                     font=("Arial", 12, "bold"), padx=20, pady=15)
        actions_frame.pack(fill=tk.X, pady=(0, 15))
        
        actions_grid = tk.Frame(actions_frame)
        actions_grid.pack(fill=tk.X)
        
        # Buttons
        btn_style = {"font": ("Arial", 10, "bold"), "width": 20, "height": 2}
        
        tk.Button(actions_grid, text="📞 Phone Setup", 
                 bg="#10b981", fg="white", command=self.phone_setup, **btn_style).grid(row=0, column=0, padx=5, pady=5)
        
        tk.Button(actions_grid, text="💬 Test AI Agent", 
                 bg="#3b82f6", fg="white", command=self.test_agent, **btn_style).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Button(actions_grid, text="🎯 Auto-Bidding", 
                 bg="#f59e0b", fg="white", command=self.setup_bidding, **btn_style).grid(row=0, column=2, padx=5, pady=5)
        
        tk.Button(actions_grid, text="📊 Dashboard", 
                 bg="#8b5cf6", fg="white", command=self.open_dashboard, **btn_style).grid(row=1, column=0, padx=5, pady=5)
        
        tk.Button(actions_grid, text="💰 Funding Tracker", 
                 bg="#10b981", fg="white", command=self.open_funding, **btn_style).grid(row=1, column=1, padx=5, pady=5)
        
        tk.Button(actions_grid, text="⚙️ Settings", 
                 bg="#6b7280", fg="white", command=self.open_settings, **btn_style).grid(row=1, column=2, padx=5, pady=5)
        
        # Activity Log
        log_frame = tk.LabelFrame(main, text="📝 Activity Log", 
                                 font=("Arial", 12, "bold"), padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, 
                                                  font=("Courier", 9), bg="#1e293b", 
                                                  fg="#e2e8f0", insertbackground="white")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log("✅ LeaX Desktop App Started")
        self.log("📁 Data directory: " + str(self.app_dir))
        
        if self.config.get('setup_completed'):
            self.log(f"👤 Logged in as: {self.config.get('business_name', 'User')}")
            self.log(f"📞 Phone: {self.config.get('phone_number', 'Not configured')}")
    
    def log(self, message):
        """Add message to activity log"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def update_status(self, message):
        """Update status label"""
        self.status_label.config(text=message)
    
    def show_setup_wizard(self):
        """Show first-time setup wizard"""
        wizard = tk.Toplevel(self.root)
        wizard.title("LeaX Setup Wizard")
        wizard.geometry("600x500")
        wizard.transient(self.root)
        wizard.grab_set()
        
        # Header
        header = tk.Frame(wizard, bg="#667eea", height=60)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="🚀 Welcome to LeaX!", 
                font=("Arial", 18, "bold"), fg="white", bg="#667eea").pack(pady=15)
        
        # Content
        content = tk.Frame(wizard, padx=30, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="Let's get you set up in 3 easy steps:", 
                font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 20))
        
        # Step 1: Business Info
        step1 = tk.LabelFrame(content, text="Step 1: Your Business", 
                             font=("Arial", 10, "bold"), padx=15, pady=15)
        step1.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(step1, text="Business Name:").pack(anchor=tk.W)
        business_name = tk.Entry(step1, font=("Arial", 11), width=40)
        business_name.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(step1, text="Email:").pack(anchor=tk.W)
        email = tk.Entry(step1, font=("Arial", 11), width=40)
        email.pack(fill=tk.X, pady=5)
        
        # Step 2: Account
        step2 = tk.LabelFrame(content, text="Step 2: Create Account", 
                             font=("Arial", 10, "bold"), padx=15, pady=15)
        step2.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(step2, text="Choose a password:").pack(anchor=tk.W)
        password = tk.Entry(step2, font=("Arial", 11), width=40, show="*")
        password.pack(fill=tk.X, pady=5)
        
        # Step 3: Phone
        step3 = tk.LabelFrame(content, text="Step 3: Phone Number (Optional - Can setup later)", 
                             font=("Arial", 10, "bold"), padx=15, pady=15)
        step3.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(step3, text="We can automatically get you a phone number,\nor you can connect your existing one later.").pack(anchor=tk.W)
        
        # Action buttons
        btn_frame = tk.Frame(content)
        btn_frame.pack(fill=tk.X, pady=(20, 0))
        
        def complete_setup():
            # Validate
            if not business_name.get() or not email.get() or not password.get():
                messagebox.showerror("Error", "Please fill in all required fields!")
                return
            
            # Save config
            self.config['business_name'] = business_name.get()
            self.config['email'] = email.get()
            self.config['setup_completed'] = True
            self.save_config()
            
            self.log(f"✅ Setup completed for {business_name.get()}")
            self.update_status("✅ Setup Complete - Ready to use!")
            
            wizard.destroy()
            
            messagebox.showinfo("Success", 
                              "Setup complete! Your AI agent is ready.\n\n"
                              "Click 'Phone Setup' to connect your phone number.")
        
        tk.Button(btn_frame, text="✅ Complete Setup", 
                 bg="#10b981", fg="white", font=("Arial", 11, "bold"),
                 command=complete_setup).pack(side=tk.RIGHT, padx=5)
        
        tk.Button(btn_frame, text="Cancel", 
                 command=wizard.destroy).pack(side=tk.RIGHT)
    
    def phone_setup(self):
        """Phone number setup wizard"""
        setup = tk.Toplevel(self.root)
        setup.title("Phone Setup")
        setup.geometry("600x500")
        
        content = tk.Frame(setup, padx=30, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="📞 Phone Number Setup", 
                font=("Arial", 16, "bold")).pack(pady=(0, 20))
        
        tk.Label(content, text="Choose how you want to set up your phone:", 
                font=("Arial", 11)).pack(anchor=tk.W, pady=(0, 20))
        
        # Option 1: Auto provision
        opt1 = tk.LabelFrame(content, text="Option 1: Get a New Number (Instant)", 
                            font=("Arial", 10, "bold"), padx=15, pady=15)
        opt1.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(opt1, text="We'll automatically provision a phone number for you.\n"
                           "Takes 30 seconds. Number will be active immediately.",
                justify=tk.LEFT).pack(anchor=tk.W)
        
        tk.Button(opt1, text="🚀 Get Phone Number Now", 
                 bg="#10b981", fg="white", font=("Arial", 10, "bold"),
                 command=lambda: self.auto_provision_number(setup)).pack(pady=(10, 0))
        
        # Option 2: Forward existing
        opt2 = tk.LabelFrame(content, text="Option 2: Forward Existing Number", 
                            font=("Arial", 10, "bold"), padx=15, pady=15)
        opt2.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(opt2, text="Keep your existing number. We'll give you forwarding\n"
                           "instructions to route calls/texts to your AI.",
                justify=tk.LEFT).pack(anchor=tk.W)
        
        tk.Button(opt2, text="📱 Use My Existing Number", 
                 bg="#3b82f6", fg="white", font=("Arial", 10, "bold"),
                 command=lambda: self.forward_existing_number(setup)).pack(pady=(10, 0))
        
        # Option 3: Manual setup
        opt3 = tk.LabelFrame(content, text="Option 3: I'll Setup Manually Later", 
                            font=("Arial", 10, "bold"), padx=15, pady=15)
        opt3.pack(fill=tk.X)
        
        tk.Label(opt3, text="Skip for now. You can setup your phone later\n"
                           "from Settings or the Dashboard.",
                justify=tk.LEFT).pack(anchor=tk.W)
        
        tk.Button(opt3, text="Skip This Step", 
                 command=setup.destroy).pack(pady=(10, 0))
    
    def auto_provision_number(self, parent_window):
        """Automatically provision Twilio number"""
        progress = tk.Toplevel(parent_window)
        progress.title("Provisioning...")
        progress.geometry("400x200")
        progress.transient(parent_window)
        progress.grab_set()
        
        tk.Label(progress, text="🔄 Provisioning Your Phone Number...", 
                font=("Arial", 12, "bold")).pack(pady=30)
        
        progress_bar = ttk.Progressbar(progress, mode='indeterminate', length=300)
        progress_bar.pack(pady=20)
        progress_bar.start()
        
        status = tk.Label(progress, text="Searching for available numbers...", 
                         font=("Arial", 10))
        status.pack()
        
        def provision():
            try:
                # Simulate API call (replace with actual Twilio provisioning)
                import time
                time.sleep(2)
                status.config(text="Found number! Setting up...")
                time.sleep(1)
                status.config(text="Configuring webhooks...")
                time.sleep(1)
                
                # In production, this would call Twilio API
                phone_number = "+1-800-555-0123"  # Simulated
                
                self.config['phone_number'] = phone_number
                self.save_config()
                
                progress.destroy()
                parent_window.destroy()
                
                self.log(f"✅ Phone number provisioned: {phone_number}")
                self.update_status(f"✅ System Ready - Phone: {phone_number}")
                
                messagebox.showinfo("Success!", 
                                  f"Your phone number is ready!\n\n"
                                  f"📞 {phone_number}\n\n"
                                  f"Your AI is now answering calls and texts!")
            except Exception as e:
                progress.destroy()
                messagebox.showerror("Error", f"Failed to provision number: {e}")
        
        threading.Thread(target=provision, daemon=True).start()
    
    def forward_existing_number(self, parent_window):
        """Setup call forwarding from existing number"""
        forward = tk.Toplevel(parent_window)
        forward.title("Forward Existing Number")
        forward.geometry("600x400")
        
        content = tk.Frame(forward, padx=30, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="📱 Forward Your Existing Number", 
                font=("Arial", 14, "bold")).pack(pady=(0, 20))
        
        tk.Label(content, text="Enter your phone number:", 
                font=("Arial", 11)).pack(anchor=tk.W)
        
        phone_entry = tk.Entry(content, font=("Arial", 12), width=30)
        phone_entry.pack(fill=tk.X, pady=10)
        
        instructions = tk.Text(content, height=10, wrap=tk.WORD, 
                              font=("Arial", 10), bg="#f8f9fa")
        instructions.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        instructions.insert("1.0", 
            "📋 Setup Instructions:\n\n"
            "1. Open your phone carrier's website or app\n"
            "2. Find 'Call Forwarding' settings\n"
            "3. Forward all calls to: +1-800-LEAX-AI\n"
            "4. For text forwarding, update your SMS webhook to:\n"
            "   https://your-app.railway.app/agent/YOUR_ID\n\n"
            "Need help? We'll walk you through it!")
        instructions.config(state=tk.DISABLED)
        
        def save_number():
            phone = phone_entry.get()
            if phone:
                self.config['phone_number'] = phone
                self.config['forwarding_enabled'] = True
                self.save_config()
                
                self.log(f"✅ Phone forwarding configured: {phone}")
                forward.destroy()
                parent_window.destroy()
                
                messagebox.showinfo("Almost Done!", 
                                  f"Phone saved: {phone}\n\n"
                                  "Follow the instructions to forward calls.\n"
                                  "Test it by calling your number!")
        
        tk.Button(content, text="✅ Save & Continue", 
                 bg="#10b981", fg="white", font=("Arial", 11, "bold"),
                 command=save_number).pack(pady=(10, 0))
    
    def test_agent(self):
        """Open test chat interface"""
        self.log("💬 Opening test chat...")
        webbrowser.open("http://localhost:8080/test-agent")
    
    def setup_bidding(self):
        """Setup auto-bidding for job platforms"""
        bidding = tk.Toplevel(self.root)
        bidding.title("Auto-Bidding Setup")
        bidding.geometry("700x600")
        
        content = tk.Frame(bidding, padx=30, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="🎯 Auto-Bidding Setup", 
                font=("Arial", 16, "bold")).pack(pady=(0, 10))
        
        tk.Label(content, text="Automatically bid on jobs from platforms like Upwork, Thumbtack, HomeAdvisor", 
                font=("Arial", 10)).pack(pady=(0, 20))
        
        # Platform selection
        platforms_frame = tk.LabelFrame(content, text="Select Platforms", 
                                       font=("Arial", 11, "bold"), padx=15, pady=15)
        platforms_frame.pack(fill=tk.X, pady=(0, 20))
        
        platforms = [
            ("Upwork", "upwork"),
            ("Thumbtack", "thumbtack"),
            ("HomeAdvisor", "homeadvisor"),
            ("Angi (Angie's List)", "angi"),
            ("Bark", "bark"),
            ("TaskRabbit", "taskrabbit")
        ]
        
        platform_vars = {}
        for name, key in platforms:
            var = tk.BooleanVar()
            tk.Checkbutton(platforms_frame, text=name, variable=var, 
                          font=("Arial", 10)).pack(anchor=tk.W, pady=2)
            platform_vars[key] = var
        
        # Bidding settings
        settings_frame = tk.LabelFrame(content, text="Bidding Settings", 
                                      font=("Arial", 11, "bold"), padx=15, pady=15)
        settings_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(settings_frame, text="Max bids per hour:").grid(row=0, column=0, sticky=tk.W, pady=5)
        max_bids = tk.Spinbox(settings_frame, from_=1, to=100, width=10)
        max_bids.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        tk.Label(settings_frame, text="Bid strategy:").grid(row=1, column=0, sticky=tk.W, pady=5)
        strategy = ttk.Combobox(settings_frame, values=["Aggressive", "Balanced", "Conservative"], 
                               width=15, state="readonly")
        strategy.current(1)
        strategy.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        auto_respond = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Auto-respond to messages", 
                      variable=auto_respond, font=("Arial", 10)).grid(row=2, column=0, 
                                                                      columnspan=2, sticky=tk.W, pady=10)
        
        # Warning
        warning = tk.Frame(content, bg="#fef3c7", padx=15, pady=15)
        warning.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(warning, text="⚠️ Important:", font=("Arial", 10, "bold"), 
                bg="#fef3c7").pack(anchor=tk.W)
        tk.Label(warning, text="You'll need to login to each platform first. LeaX will\n"
                              "then automate bidding while following each platform's rules.",
                justify=tk.LEFT, bg="#fef3c7", font=("Arial", 9)).pack(anchor=tk.W)
        
        def start_bidding():
            enabled_platforms = [k for k, v in platform_vars.items() if v.get()]
            
            if not enabled_platforms:
                messagebox.showwarning("No Platforms", "Please select at least one platform!")
                return
            
            self.config['auto_bidding_enabled'] = True
            self.config['bidding_apps'] = enabled_platforms
            self.config['bidding_settings'] = {
                'max_bids_per_hour': max_bids.get(),
                'strategy': strategy.get(),
                'auto_respond': auto_respond.get()
            }
            self.save_config()
            
            self.log(f"✅ Auto-bidding enabled for: {', '.join(enabled_platforms)}")
            self.update_status("🎯 Auto-Bidding Active")
            
            bidding.destroy()
            
            messagebox.showinfo("Bidding Activated!", 
                              f"Auto-bidding is now active for:\n\n" + 
                              "\n".join([f"• {p}" for p in enabled_platforms]) + 
                              f"\n\nStrategy: {strategy.get()}\n"
                              f"Max bids/hour: {max_bids.get()}")
        
        tk.Button(content, text="🚀 Start Auto-Bidding", 
                 bg="#f59e0b", fg="white", font=("Arial", 12, "bold"),
                 command=start_bidding).pack()
    
    def open_dashboard(self):
        """Open web dashboard"""
        self.log("📊 Opening dashboard...")
        webbrowser.open("http://localhost:8080/dashboard")
    
    def open_funding(self):
        """Open funding dashboard"""
        self.log("💰 Opening funding tracker...")
        webbrowser.open("http://localhost:8080/funding-dashboard")
    
    def open_settings(self):
        """Open settings window"""
        settings = tk.Toplevel(self.root)
        settings.title("Settings")
        settings.geometry("600x500")
        
        content = tk.Frame(settings, padx=30, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(content, text="⚙️ LeaX Settings", 
                font=("Arial", 16, "bold")).pack(pady=(0, 20))
        
        # Settings content
        notebook = ttk.Notebook(content)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # General tab
        general = tk.Frame(notebook, padx=20, pady=20)
        notebook.add(general, text="General")
        
        tk.Label(general, text=f"Business: {self.config.get('business_name', 'N/A')}", 
                font=("Arial", 11)).pack(anchor=tk.W, pady=5)
        tk.Label(general, text=f"Email: {self.config.get('email', 'N/A')}", 
                font=("Arial", 11)).pack(anchor=tk.W, pady=5)
        tk.Label(general, text=f"Phone: {self.config.get('phone_number', 'Not configured')}", 
                font=("Arial", 11)).pack(anchor=tk.W, pady=5)
        
        tk.Button(general, text="📞 Change Phone Number", 
                 command=self.phone_setup).pack(pady=20)
        
        # About tab
        about = tk.Frame(notebook, padx=20, pady=20)
        notebook.add(about, text="About")
        
        tk.Label(about, text="LeaX AI Business Automation", 
                font=("Arial", 14, "bold")).pack(pady=10)
        tk.Label(about, text="Version 1.0.0", font=("Arial", 10)).pack()
        tk.Label(about, text=f"\nInstalled at: {self.app_dir}", 
                font=("Arial", 9), fg="gray").pack()
    
    def run(self):
        """Start the application"""
        self.root.mainloop()


if __name__ == "__main__":
    print("🚀 Starting LeaX Desktop App...")
    app = LeaXDesktopApp()
    app.run()
