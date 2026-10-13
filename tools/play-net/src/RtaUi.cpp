// What this build adds to the application's windows. See Rta.h.
#include "Rta.h"

#include <QAction>
#include <QApplication>
#include <QCheckBox>
#include <QCloseEvent>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGridLayout>
#include <QInputDialog>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QSettings>
#include <QSpinBox>
#include <QStackedWidget>
#include <QMainWindow>
#include <QMenu>
#include <QMenuBar>
#include <QPointer>
#include <QTimer>
#include <QVBoxLayout>

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <memory>
#include <thread>

#include "AppConfig.h"

#define PREF_RTA_CONTROLS_SHOWN "rta.ui.controlsshown"

namespace
{
	// The keyboard as ControllerConfigDialog::AutoConfigureKeyboard sets it up (see
	// play-net.patch), and the controller as RtaPad.mm reads it. Keep the three in step.
	QString ControlsText()
	{
		QString controller = QString::fromStdString(Rta::GamePadName());
		QString text;
		text += "<h3>Controller</h3>";
		if(controller.isEmpty())
			text += "<p>No game controller is attached. Plug one in (USB) or pair it (Bluetooth) at any time - "
			        "DualSense, DualShock 4, Xbox, Switch Pro and others that macOS knows work at once, with nothing to set up: "
			        "sticks, direction pad and buttons are where they are on a PlayStation pad; Options or Menu is Start, "
			        "Create, Share or View is Select (so is pressing a Sony pad's touchpad).</p>";
		else
			text += QString("<p><b>%1</b> is attached and is the pad in port 1: sticks, direction pad and buttons are where they "
			                "are on a PlayStation pad; Options or Menu is Start, Create, Share or View is Select (so is pressing "
			                "a Sony pad's touchpad). It is listened to while this window is in front.</p>")
			            .arg(controller.toHtmlEscaped());
		text += "<h3>Keyboard</h3>"
		        "<table cellspacing='0' cellpadding='3'>"
		        "<tr><td><b>Move</b> (left stick)</td><td>W&nbsp;A&nbsp;S&nbsp;D</td><td width='24'></td><td><b>Direction pad</b> (menus)</td><td>arrow keys</td></tr>"
		        "<tr><td>&#10005; cross</td><td>K</td><td></td><td>&#9675; circle</td><td>L</td></tr>"
		        "<tr><td>&#9633; square</td><td>J</td><td></td><td>&#9651; triangle</td><td>I</td></tr>"
		        "<tr><td>L1</td><td>Q</td><td></td><td>R1</td><td>E</td></tr>"
		        "<tr><td>L2</td><td>1</td><td></td><td>R2</td><td>3</td></tr>"
		        "<tr><td>L3 (press left stick)</td><td>X</td><td></td><td>R3 (press right stick)</td><td>C</td></tr>"
		        "<tr><td>Camera (right stick)</td><td>T&nbsp;F&nbsp;G&nbsp;H</td><td></td><td>Start / Select</td><td>Return / Backspace</td></tr>"
		        "</table>"
		        "<p>The four face buttons lie on I&nbsp;J&nbsp;K&nbsp;L as they lie on the pad: I on top, J left, K below, L right.<br>"
		        "Full screen: double-click the picture; Escape leaves it.<br>"
		        "Other keys, or a controller macOS does not know: <i>Settings &rarr; Controller Manager</i>.</p>";
		return text;
	}

	QPointer<QDialog> g_controls;
	QPointer<QWidget> g_mainWindow;
	// tests (--rta-test-dialogs): how often the Controls window was told that a modal window
	// of ours blocks it, and whether it is so now
	int g_controlsBlocked = 0;
	bool g_controlsBlockedNow = false;
	bool g_controlsWanted = false; // asked for while a question was up: shown when that is answered
	class CBlockWatch : public QObject
	{
	public:
		using QObject::QObject;
		bool eventFilter(QObject*, QEvent* event) override
		{
			if(event->type() == QEvent::WindowBlocked)
			{
				g_controlsBlocked++;
				g_controlsBlockedNow = true;
			}
			if(event->type() == QEvent::WindowUnblocked) g_controlsBlockedNow = false;
			return false;
		}
	};
	// a test run's windows say that they are one and never take the keyboard
	void MarkTestWindow(QWidget* window)
	{
		if(!Rta::IsTestRun() || Rta::TestDialogs() == 0) return;
		window->setWindowTitle(QString::fromStdString(Rta::WindowTitle(window->windowTitle().toStdString())));
		window->setAttribute(Qt::WA_ShowWithoutActivating, true);
	}
	bool g_askingName = false;

	// the one-step log-in's windows (further down)
	QLineEdit* BuildPlayerName(QDialog& dialog, const std::string& why);
	QDialog* BuildGameCode(QWidget* parent, const std::string& code);
	struct GameDialog
	{
		QDialog* dialog = nullptr;
		QLineEdit* code = nullptr;     // Join only
		QCheckBox* choose = nullptr;   // null when no character is known: the screens come up anyway
	};
	GameDialog BuildGameDialog(QWidget* parent, bool join, const QString& typed);
	QMessageBox* BuildSetWarning(QWidget* parent, const QString& text);
}

void Rta::ShowControls(QWidget* parent)
{
	if(g_controls)
	{
		g_controls->raise();
		if(!Rta::IsTestRun()) g_controls->activateWindow();
		return;
	}
	// Never while a question of ours is up: a window opened then takes no input (the
	// window system blocks it: its Close button is dead) and lies round the question like
	// a second thing to deal with (docs/issues/mac-app-start.md, "The name dialog"). It
	// comes when the question has been answered.
	if(Rta::TestDialogs() != 2 && (g_askingName || QApplication::activeModalWidget()))
	{
		g_controlsWanted = true;
		Rta::LogLine("controls: asked for while a question is up; shown when it has been answered");
		return;
	}
	g_controlsWanted = false;
	auto dialog = new QDialog(parent);
	dialog->setAttribute(Qt::WA_DeleteOnClose, true);
	dialog->setWindowTitle("Controls");
	MarkTestWindow(dialog);
	dialog->installEventFilter(new CBlockWatch(dialog));
	g_controlsBlocked = 0;
	g_controlsBlockedNow = false;
	Rta::LogLine("controls: the window with the keys and the controller's buttons is shown");
	auto layout = new QVBoxLayout(dialog);
	auto label = new QLabel(ControlsText(), dialog);
	label->setTextFormat(Qt::RichText);
	label->setWordWrap(true);
	label->setMinimumWidth(520);
	layout->addWidget(label);
	auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
	QObject::connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::close);
	layout->addWidget(buttons);
	// the controller's name follows what is attached while the window is open
	auto timer = new QTimer(dialog);
	QObject::connect(timer, &QTimer::timeout, label, [label]() {
		auto text = ControlsText();
		if(label->text() != text) label->setText(text);
	});
	timer->start(1000);
	g_controls = dialog;
	// not modal: the game goes on, and the keys can be tried while it is read
	dialog->show();
}

// ---- the disc image ----------------------------------------------------------------------

namespace
{
	std::function<void(const std::string&)> g_discBoot;
}

void Rta::SetDiscBoot(const std::function<void(const std::string&)>& boot)
{
	g_discBoot = boot;
}

// ---- nothing that macOS may hold runs on the application's own thread (Rta.h) --------------

namespace
{
	std::atomic<bool> g_quitting{false};
	int g_discSearch = 0; // counts every start of a look for the disc image: a later one ends an earlier one

	// Runs 'work' on a thread of its own while the application's windows stay alive
	// (a local event loop). False: the application is ending - the thread is then left
	// to itself, so 'work' may hold nothing by reference.
	template <typename T>
	bool RunAside(const std::function<T()>& work, T& result)
	{
		struct Shared
		{
			std::atomic<bool> done{false};
			T result{};
		};
		auto shared = std::make_shared<Shared>();
		std::thread([shared, work]() {
			shared->result = work();
			shared->done = true;
		}).detach();
		QEventLoop loop;
		QTimer timer;
		QObject::connect(&timer, &QTimer::timeout, &loop, [&loop, shared]() {
			if(shared->done) loop.quit();
		});
		timer.start(25);
		loop.exec();
		// a loop that ended before the work did was ended by the application's quit
		if(!shared->done)
		{
			g_quitting = true;
			return false;
		}
		result = shared->result;
		return !g_quitting;
	}

	// so many milliseconds with the windows alive; false: the application is ending
	bool Pause(int milliseconds)
	{
		QEventLoop loop;
		bool timedOut = false;
		QTimer::singleShot(milliseconds, &loop, [&]() {
			timedOut = true;
			loop.quit();
		});
		loop.exec();
		if(!timedOut) g_quitting = true;
		return timedOut && !g_quitting;
	}
}

bool Rta::Quitting()
{
	return g_quitting;
}

bool Rta::WaitReadable(QWidget*, const std::string& path, const std::string& what, int* errorOut)
{
	int mine = g_discSearch;
	bool refused = false;
	if(errorOut) *errorOut = 0;
	for(;;)
	{
		int error = 0;
		if(!RunAside<int>([path, what]() { return Rta::ProbeReadable(path, what); }, error)) return false;
		if(mine != g_discSearch)
		{
			Rta::SetNotice("disc", "");
			return false; // another image was chosen meanwhile
		}
		if(error == 0)
		{
			if(refused) Rta::LogLine(path + " can be read now");
			Rta::SetNotice("disc", "");
			return true;
		}
		if(error != EACCES && error != EPERM)
		{
			Rta::LogLine(path + " cannot be opened: " + strerror(error));
			Rta::SetNotice("disc", "");
			if(errorOut) *errorOut = error;
			return false;
		}
		if(!refused) Rta::LogLine(path + " may not be read (" + strerror(error) + "): the window says so; it is tried again every two seconds");
		refused = true;
		Rta::SetNotice("disc", Rta::DeniedText(path, what, error));
		if(!Pause(2000)) return false;
		if(mine != g_discSearch)
		{
			Rta::SetNotice("disc", "");
			return false;
		}
	}
}

void Rta::BootDiscWhenReadable(QWidget* parent, const std::string& path)
{
	g_discSearch++;
	int error = 0;
	if(Rta::WaitReadable(parent, path, "Your disc image", &error))
		Rta::BootDisc(path);
	else if(error != 0)
		Rta::SetNotice("disc", "The disc image that was named cannot be opened (" + std::string(strerror(error)) + "): " + path);
}

void Rta::BootDisc(const std::string& path)
{
	if(g_discBoot && !path.empty()) g_discBoot(path);
}

std::string Rta::ChooseDisc(QWidget* parent, const std::string& given, bool askAnew)
{
	auto info = Rta::GetLaunchInfo();
	if(!info.packaged) return std::string();
	// Every opening of the image, and the whole search for one, runs on a thread of its
	// own (WaitReadable, RunAside): macOS holds a program inside the first opening of
	// anything under Desktop, Documents or Downloads until the person has answered its
	// question, and the window has to stay alive and say so. A later call (the menu) ends
	// an earlier one that is still waiting.
	int mine = ++g_discSearch;
	auto ended = [mine]() { return g_quitting || mine != g_discSearch; };
	auto check = [](const std::string& path) {
		std::string verdict = "the application is ending";
		RunAside<std::string>([path]() { return Rta::CheckDisc(path); }, verdict);
		return verdict;
	};
	QSettings launch(QString::fromStdString(info.root + "/launch.ini"), QSettings::IniFormat);
	auto accept = [&launch, &info](const QString& path) {
		launch.setValue("disc", path);
		launch.sync();
		Rta::LogLine("disc image accepted: " + path.toStdString());
		std::string guarded = Rta::GuardedFolderOf(path.toStdString());
		if(!guarded.empty())
			Rta::LogLine("disc image: it is under " + guarded + ", which macOS lets a program read only after asking the person - again after every new build of an application signed without an identity. Beside the application or in " + info.root + " no question is asked (docs/issues/mac-app-start.md)");
		return path.toStdString();
	};
	if(!askAnew)
	{
		// the one given, else the one remembered
		QString candidate = given.empty() ? QString::fromStdString(info.disc) : QString::fromStdString(given);
		int error = 0;
		bool readable = !candidate.isEmpty() && Rta::WaitReadable(parent, candidate.toStdString(), "Your disc image", &error);
		if(ended()) return std::string();
		if(!candidate.isEmpty() && !readable && error == ENOENT)
			Rta::LogLine("the disc image that was " + std::string(given.empty() ? "used last" : "named") + " is not there any more: " + candidate.toStdString() + "; looking for one");
		else if(!candidate.isEmpty())
		{
			std::string verdict = readable ? check(candidate.toStdString()) : "'" + candidate.toStdString() + "' cannot be opened.";
			if(ended()) return std::string();
			if(verdict.empty()) return accept(candidate);
			Rta::LogLine("disc image REFUSED: " + verdict);
			// a wrong file named for a test run: nobody is there to do anything about it
			if(!given.empty() && Rta::IsTestRun()) return std::string();
		}
	}
	for(;;)
	{
		if(!askAnew)
		{
			// Nobody is asked to choose a file: it is looked for. Only when there is none,
			// one window says where to put it.
			std::string found;
			RunAside<std::string>([]() { return Rta::FindDisc(); }, found);
			if(ended()) return std::string();
			if(!found.empty()) return accept(QString::fromStdString(found));
			Rta::LogLine("no disc image: the window that says where to put it (Retry, Browse)");
			QMessageBox box(parent);
			box.setIcon(QMessageBox::Information);
			box.setWindowTitle("Game image needed");
			box.setText("Put the game image in the same folder as this app, or in Downloads, then press Retry.");
			box.setInformativeText("It is your own disc image of Champions: Return to Arms - the US release, SLUS-20973, version 2.00: one file of about 4.3 GB, such as an .iso, under any name. "
			                       "Nothing of the game is part of this application.\n\nThe Desktop and Documents folders are looked in as well. "
			                       "macOS may ask once whether this app may read those folders: allow it, or keep the file beside the app.");
			auto retry = box.addButton("Retry", QMessageBox::AcceptRole);
			auto browse = box.addButton("Browse...", QMessageBox::ActionRole);
			box.addButton("Not now", QMessageBox::RejectRole);
			box.setDefaultButton(retry);
			box.exec();
			if(ended()) return std::string();
			if(box.clickedButton() == retry) continue;
			if(box.clickedButton() != browse)
			{
				Rta::LogLine("no disc image: left for later");
				return std::string();
			}
		}
		Rta::LogLine("asking for the disc image (file dialog)");
		QString start = launch.value("discdir", QDir::homePath()).toString();
		QString candidate = QFileDialog::getOpenFileName(parent, "Choose your disc image of Champions: Return to Arms (SLUS-20973, version 2.00)", start,
		                                                 "Disc images (*.iso *.bin *.cue *.chd *.cso *.zso *.isz *.img *.mdf);;All files (*)");
		if(candidate.isEmpty())
		{
			Rta::LogLine("no disc image chosen");
			if(askAnew) return std::string();
			continue;
		}
		launch.setValue("discdir", QFileInfo(candidate).absolutePath());
		// a file the person picked in the system's own dialog: macOS lets the application read it
		std::string verdict = check(candidate.toStdString());
		if(ended()) return std::string();
		if(verdict.empty()) return accept(candidate);
		Rta::LogLine("disc image REFUSED: " + verdict);
		// in a test run nobody is there to pick another one
		if(Rta::IsTestRun()) return std::string();
		QMessageBox::warning(parent, "Not the right disc", QString::fromStdString(verdict));
	}
}

// ---- Online ------------------------------------------------------------------------------

namespace
{
	struct OnlineDialog
	{
		QDialog* dialog = nullptr;
		QLineEdit* server = nullptr;
		QSpinBox* player = nullptr;
		QCheckBox* atStart = nullptr;
	};

	OnlineDialog BuildOnline(QWidget* parent, const Rta::LaunchInfo& info)
	{
		OnlineDialog result;
		result.dialog = new QDialog(parent);
		QDialog& dialog = *result.dialog;
		dialog.setWindowTitle("Online");
		auto layout = new QVBoxLayout(&dialog);
		auto form = new QFormLayout();
		layout->addLayout(form);

		auto server = new QLineEdit(QString::fromStdString(info.server), &dialog);
		server->setPlaceholderText("empty: the server runs on this computer");
		server->setMinimumWidth(320);
		server->setEnabled(info.packaged);
		form->addRow("Lobby server address:", server);
		auto serverNote = new QLabel(QString("An IPv4 address or a host name; everyone in a game uses the same one.%1")
		                                 .arg(info.serverNow.empty() ? "" : QString(" This run talks to: %1.").arg(QString::fromStdString(info.serverNow).toHtmlEscaped())),
		                             &dialog);
		serverNote->setWordWrap(true);
		form->addRow("", serverNote);

		auto player = new QSpinBox(&dialog);
		player->setRange(1, 99);
		player->setValue(info.player);
		player->setEnabled(info.packaged);
		form->addRow("Player number:", player);
		auto playerNote = new QLabel("Leave it at 1. Each number has its own settings and memory card; another number is only for a second copy on the same Mac.", &dialog);
		playerNote->setWordWrap(true);
		form->addRow("", playerNote);

		// the one-step log-in: the player name kept for this server, and whether the
		// application goes online by itself when it starts
		QString saved = QString::fromStdString(Rta::OnlineSavedName());
		auto playerName = new QLabel(saved.isEmpty() ? QString("none yet: you are asked for one the first time you go online") : QString("<b>%1</b>").arg(saved.toHtmlEscaped()), &dialog);
		playerName->setWordWrap(true);
		form->addRow("Player name:", playerName);
		auto playerNameNote = new QLabel("What the others see. It is kept for this server on this Mac, with a password the application makes itself; "
		                                 "<i>Online &rarr; Forget online login</i> removes both.",
		                                 &dialog);
		playerNameNote->setWordWrap(true);
		form->addRow("", playerNameNote);
		auto atStart = new QCheckBox("Go online when the application starts (title screen to lobby by itself)", &dialog);
		atStart->setChecked(info.packaged ? Rta::OnlineAtStart() : false);
		atStart->setEnabled(info.packaged);
		if(!info.packaged) atStart->setToolTip("Started by play.sh: its --online option does this.");
		form->addRow("", atStart);
		result.atStart = atStart;

		QString patchText = info.patchSet.empty() ? QString("none loaded") : QString::fromStdString(info.patchSet);
		if(!info.patchSet.empty() && !info.gameChecked) patchText += "  (not applied: the game is not loaded)";
		auto patchSet = new QLabel(QString("<b>%1</b>").arg(patchText.toHtmlEscaped()), &dialog);
		patchSet->setTextInteractionFlags(Qt::TextSelectableByMouse);
		form->addRow("Patch set:", patchSet);
		auto patchNote = new QLabel("Compare the figure after \"set\" with your friends' before you start: every player in a game has to have the same.", &dialog);
		patchNote->setWordWrap(true);
		form->addRow("", patchNote);

		QString signin;
		if(!info.signinPatch.empty() && QString::fromStdString(info.signinPatch).startsWith(QString::fromStdString(Rta::BundleResourcePath()) + "/"))
			signin = "found, inside this application";
		else if(!info.signinPatch.empty())
			signin = QString("found, in %1").arg(dialog.fontMetrics().elidedText(QFileInfo(QString::fromStdString(info.signinPatch)).absolutePath(), Qt::ElideMiddle, 360).toHtmlEscaped());
		else
			signin = QString("<b>not found.</b> Without it the game stops with a network error after \"Internet Game\" (the sign-in servers of 2005 are gone). "
			                 "It is not part of this application. If you have the file <tt>SLUS-20973_4028A55F_signin.pnach</tt>, put it into one of these folders and start again:<br>%1")
			             .arg(QString::fromStdString(info.signinPlaces).trimmed().toHtmlEscaped().replace("\n", "<br>"));
		auto signinLabel = new QLabel(signin, &dialog);
		signinLabel->setWordWrap(true);
		signinLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
		form->addRow("Sign-in patch:", signinLabel);

		if(info.packaged)
		{
			// a path has no place to break a line at: the name, and the folder shortened in the middle
			QString discText = "none chosen yet";
			if(!info.disc.empty())
			{
				QFileInfo file(QString::fromStdString(info.disc));
				discText = file.fileName() + "\nin " + dialog.fontMetrics().elidedText(file.absolutePath(), Qt::ElideMiddle, 400);
			}
			auto disc = new QLabel(discText, &dialog);
			disc->setTextFormat(Qt::PlainText);
			disc->setToolTip(QString::fromStdString(info.disc));
			disc->setTextInteractionFlags(Qt::TextSelectableByMouse);
			form->addRow("Disc image:", disc);
		}
		else
		{
			auto note = new QLabel("This copy was started by play.sh: the server and the player are its --server and --player options, going online at the start its --online option.", &dialog);
			note->setWordWrap(true);
			layout->addWidget(note);
		}

		auto buttons = new QDialogButtonBox(info.packaged ? (QDialogButtonBox::Save | QDialogButtonBox::Cancel) : QDialogButtonBox::Close, &dialog);
		QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
		QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
		layout->addWidget(buttons);
		result.server = server;
		result.player = player;
		return result;
	}
}

void Rta::ShowOnline(QWidget* parent)
{
	auto info = Rta::GetLaunchInfo();
	auto online = BuildOnline(parent, info);
	std::unique_ptr<QDialog> dialog(online.dialog);
	if(dialog->exec() != QDialog::Accepted || !info.packaged) return;

	std::string newServer = online.server->text().trimmed().toStdString();
	int newPlayer = online.player->value();
	if(online.atStart->isChecked() != Rta::OnlineAtStart()) Rta::SetOnlineAtStart(online.atStart->isChecked());
	if(newServer == info.server && newPlayer == info.player) return;
	Rta::SaveLaunch(newServer, newPlayer);
	auto answer = QMessageBox::question(parent, "Online", "The change is taken up when the application starts again. The game that is running ends.\n\nStart again now?", QMessageBox::Yes | QMessageBox::No);
	if(answer == QMessageBox::Yes) Rta::Relaunch();
}

// For tests: a picture of one of our windows as it would be shown, without showing it
// to anyone ("controls", "online", "about" - the text only for the last).
bool Rta::RenderDialog(const std::string& name, const std::string& path)
{
	QWidget* parent = g_mainWindow;
	if(name == "online")
	{
		auto online = BuildOnline(parent, Rta::GetLaunchInfo());
		std::unique_ptr<QDialog> dialog(online.dialog);
		dialog->setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog->show();
		bool saved = dialog->grab().save(QString::fromStdString(path), "PNG");
		dialog->hide();
		return saved;
	}
	if(name == "playername" || name == "playername2")
	{
		QDialog dialog(parent);
		BuildPlayerName(dialog, (name == "playername2") ? "That name is taken on this server (or the server did not accept it). Choose another one." : "");
		dialog.setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog.show();
		bool saved = dialog.grab().save(QString::fromStdString(path), "PNG");
		dialog.hide();
		return saved;
	}
	if(name == "setwarning")
	{
		std::unique_ptr<QMessageBox> box(BuildSetWarning(parent, "Another player in this game has a different patch set: theirs is 1b2c3d4e (150 words), yours is df6a6139 (81 words).\n\n"
		                                                         "The game computes every frame on every machine, so with different patches the players fall out of step. "
		                                                         "Do not start the game: everyone needs the same build and the same patch list (Online > Server, player, patch set... shows yours)."));
		box->setAttribute(Qt::WA_DontShowOnScreen, true);
		box->show();
		bool saved = box->grab().save(QString::fromStdString(path), "PNG");
		box->hide();
		return saved;
	}
	if(name == "host" || name == "join")
	{
		auto game = BuildGameDialog(parent, name == "join", "KXRT");
		std::unique_ptr<QDialog> dialog(game.dialog);
		dialog->setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog->show();
		bool saved = dialog->grab().save(QString::fromStdString(path), "PNG");
		dialog->hide();
		return saved;
	}
	if(name == "gamecode")
	{
		std::unique_ptr<QDialog> dialog(BuildGameCode(parent, "KXRT"));
		dialog->setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog->show();
		bool saved = dialog->grab().save(QString::fromStdString(path), "PNG");
		dialog->hide();
		return saved;
	}
	if(name == "controls" || name == "about")
	{
		QDialog dialog(parent);
		auto layout = new QVBoxLayout(&dialog);
		auto label = new QLabel((name == "controls") ? ControlsText() : QString::fromStdString(Rta::AboutText()).trimmed(), &dialog);
		label->setTextFormat((name == "controls") ? Qt::RichText : Qt::PlainText);
		label->setWordWrap(true);
		label->setMinimumWidth(520);
		layout->addWidget(label);
		dialog.setAttribute(Qt::WA_DontShowOnScreen, true);
		dialog.show();
		bool saved = dialog.grab().save(QString::fromStdString(path), "PNG");
		dialog.hide();
		return saved;
	}
	return false;
}

// ---- one-step online: the player name ------------------------------------------------------

namespace
{
	// "Play Online" and its relatives in the menu
	void StartOnline(QWidget* parent, const std::string& mode)
	{
		std::string error;
		if(!Rta::OnlineStart(mode, error)) QMessageBox::information(parent, "Play Online", QString::fromStdString(error));
	}

	void ForgetLogin(QWidget* parent)
	{
		QString name = QString::fromStdString(Rta::OnlineSavedName());
		if(name.isEmpty()) return;
		auto answer = QMessageBox::question(parent, "Forget online login",
		                                    QString("Forget the player name \"%1\" and its password for this server?\n\n"
		                                            "The next time you go online you are asked for a player name again. The name \"%1\" stays taken on the server: "
		                                            "nobody, you included, can use it again from this application.")
		                                        .arg(name),
		                                    QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel);
		if(answer == QMessageBox::Yes) Rta::OnlineForget();
	}
}

// The one thing the player is asked for. It reads as a name, not as an account: the
// password is the application's own business and is never shown or asked for.
namespace
{
	QLineEdit* BuildPlayerName(QDialog& dialog, const std::string& why)
	{
	dialog.setWindowTitle("Player name");
	auto layout = new QVBoxLayout(&dialog);
	if(!why.empty())
	{
		auto reason = new QLabel(QString("<b>%1</b>").arg(QString::fromStdString(why).toHtmlEscaped()), &dialog);
		reason->setWordWrap(true);
		layout->addWidget(reason);
	}
	auto text = new QLabel("Your player name - what your friends see in the lobby, in a game's room and in chat:", &dialog);
	text->setWordWrap(true);
	layout->addWidget(text);
	auto edit = new QLineEdit(&dialog);
	edit->setMaxLength(15);
	edit->setPlaceholderText("3 to 15 letters and digits");
	edit->setMinimumWidth(360);
	layout->addWidget(edit);
	auto hint = new QLabel(" ", &dialog);
	hint->setWordWrap(true);
	layout->addWidget(hint);
	auto info = Rta::GetLaunchInfo();
	auto note = new QLabel(QString("<small>You are asked once: the name is kept on this Mac and registered with the lobby server%1, "
	                               "whose terms of use (the game shows them under Internet Game) are accepted for you on the way in.</small>")
	                           .arg(info.serverNow.empty() ? QString() : QString(" (%1)").arg(QString::fromStdString(info.serverNow).toHtmlEscaped())),
	                       &dialog);
	note->setWordWrap(true);
	layout->addWidget(note);
	auto buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dialog);
	buttons->button(QDialogButtonBox::Ok)->setText("Go online");
	buttons->button(QDialogButtonBox::Cancel)->setText("Not now");
	buttons->button(QDialogButtonBox::Ok)->setEnabled(false);
	QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
	QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
	layout->addWidget(buttons);
	QObject::connect(edit, &QLineEdit::textChanged, &dialog, [hint, buttons](const QString& typed) {
		std::string wrong = typed.isEmpty() ? std::string() : Rta::OnlineCheckName(typed.toStdString());
		// too short is not worth a complaint while it is being typed
		bool tooShort = typed.size() < 3;
		hint->setText((wrong.empty() || (tooShort && wrong.find("at least") != std::string::npos)) ? QString(" ") : QString::fromStdString(wrong));
		buttons->button(QDialogButtonBox::Ok)->setEnabled(!typed.isEmpty() && wrong.empty());
	});
	edit->setFocus();
	return edit;
	}

	// the code of the game this copy hosts, large, for reading out to friends
	QPointer<QDialog> g_codeWindow;
	QDialog* BuildGameCode(QWidget* parent, const std::string& code)
	{
		auto dialog = new QDialog(parent);
		dialog->setWindowTitle("Your game");
		auto layout = new QVBoxLayout(dialog);
		auto top = new QLabel("Tell your friends this code:", dialog);
		layout->addWidget(top);
		auto big = new QLabel(QString::fromStdString(code), dialog);
		auto font = big->font();
		font.setPointSize(64);
		font.setBold(true);
		font.setLetterSpacing(QFont::AbsoluteSpacing, 8);
		big->setFont(font);
		big->setAlignment(Qt::AlignCenter);
		big->setTextInteractionFlags(Qt::TextSelectableByMouse);
		layout->addWidget(big);
		auto how = new QLabel("They choose <i>Online &rarr; Join a game...</i> and type it (same server, same disc, same patch set). "
		                      "When they are in your game's room, press &#10005; <i>Start Game</i> there.",
		                      dialog);
		how->setWordWrap(true);
		how->setMinimumWidth(420);
		layout->addWidget(how);
		auto status = new QLabel(" ", dialog);
		status->setWordWrap(true);
		layout->addWidget(status);
		auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
		QObject::connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::close);
		layout->addWidget(buttons);
		// what the application is doing on the way to the room
		auto timer = new QTimer(dialog);
		QObject::connect(timer, &QTimer::timeout, status, [status]() {
			auto note = QString::fromStdString(Rta::OnlineNote());
			if(status->text() != note) status->setText(note.isEmpty() ? QString(" ") : note);
		});
		timer->start(500);
		return dialog;
	}

	// Host and Join take the character the player used last on this server from the
	// game's list of stored characters. The dialogs say which one that is and have the way
	// to the character screens instead.
	GameDialog BuildGameDialog(QWidget* parent, bool join, const QString& typed)
	{
		GameDialog result;
		result.dialog = new QDialog(parent);
		QDialog& dialog = *result.dialog;
		dialog.setWindowTitle(join ? "Join a game" : "Host a game");
		auto layout = new QVBoxLayout(&dialog);
		if(join)
		{
			layout->addWidget(new QLabel("The code of your friend's game (they see it when they choose Host a game):", &dialog));
			result.code = new QLineEdit(typed, &dialog);
			result.code->setMaxLength(8);
			result.code->setMinimumWidth(320);
			layout->addWidget(result.code);
		}
		else
		{
			auto text = new QLabel("A game of your own is opened and named with a code of four letters for your friends.", &dialog);
			text->setWordWrap(true);
			text->setMinimumWidth(380);
			layout->addWidget(text);
		}
		QString last = QString::fromStdString(Rta::OnlineLastCharacter());
		if(last.isEmpty())
		{
			auto none = new QLabel("You make or choose your character on the game's own screens; the next time it is taken by itself.", &dialog);
			none->setWordWrap(true);
			layout->addWidget(none);
		}
		else
		{
			auto with = new QLabel(QString("Your character: <b>%1</b> (the one you used last).").arg(last.toHtmlEscaped()), &dialog);
			with->setWordWrap(true);
			layout->addWidget(with);
			result.choose = new QCheckBox("Choose another character, or make a new one", &dialog);
			result.choose->setToolTip("The game's character screens are yours. (Holding any button while the game comes up does the same.)");
			layout->addWidget(result.choose);
		}
		auto buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dialog);
		buttons->button(QDialogButtonBox::Ok)->setText(join ? "Join" : "Host");
		QObject::connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
		QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
		layout->addWidget(buttons);
		if(result.code) result.code->setFocus();
		return result;
	}

	void HostGame(QWidget* parent)
	{
		std::string mode = "host";
		// nothing to ask when no character is known: the game's screens come up
		if(!Rta::OnlineLastCharacter().empty())
		{
			auto game = BuildGameDialog(parent, false, QString());
			std::unique_ptr<QDialog> dialog(game.dialog);
			if(dialog->exec() != QDialog::Accepted) return;
			if(game.choose && game.choose->isChecked()) mode += "+choose";
		}
		std::string error;
		if(!Rta::OnlineStart(mode, error)) QMessageBox::information(parent, "Host a game", QString::fromStdString(error));
	}

	void JoinGame(QWidget* parent)
	{
		QString typed;
		bool choose = false;
		for(;;)
		{
			auto game = BuildGameDialog(parent, true, typed);
			std::unique_ptr<QDialog> dialog(game.dialog);
			if(game.choose) game.choose->setChecked(choose);
			if(dialog->exec() != QDialog::Accepted) return;
			typed = game.code->text().trimmed().toUpper();
			choose = game.choose && game.choose->isChecked();
			std::string wrong = Rta::OnlineCheckCode(typed.toStdString());
			if(wrong.empty()) break;
			QMessageBox::information(parent, "Join a game", QString::fromStdString(wrong));
		}
		std::string error;
		if(!Rta::OnlineStart("join:" + typed.toStdString() + (choose ? "+choose" : ""), error)) QMessageBox::information(parent, "Join a game", QString::fromStdString(error));
	}
}

void Rta::ShowGameCode(const std::string& code)
{
	if(g_codeWindow) g_codeWindow->close();
	auto dialog = BuildGameCode(g_mainWindow, code);
	dialog->setAttribute(Qt::WA_DeleteOnClose, true);
	g_codeWindow = dialog;
	dialog->show(); // not modal: the game goes on
}

namespace
{
	// the first paragraph is the message, the rest the explanation under it (which wraps)
	QMessageBox* BuildSetWarning(QWidget* parent, const QString& text)
	{
		auto box = new QMessageBox(parent);
		box->setIcon(QMessageBox::Warning);
		box->setWindowTitle("Different patch sets");
		box->setText(text.section("\n\n", 0, 0));
		box->setInformativeText(text.section("\n\n", 1));
		box->setStandardButtons(QMessageBox::Ok);
		return box;
	}
}

void Rta::WarnPatchSet(const std::string& text)
{
	auto box = BuildSetWarning(g_mainWindow, QString::fromStdString(text));
	box->setAttribute(Qt::WA_DeleteOnClose, true);
	box->setModal(false);
	box->show(); // the game goes on
}

// The question for the player name (docs/issues/mac-app-start.md, "The name dialog").
// As released on 2026-10-13 it was a window of its own, modal for the whole application,
// and it ended without a name on "Not now", on Escape (or Command-period) and when its
// window was closed; it had no time limit and nothing of ours closed it. What went wrong
// round it: the Controls help opened by itself two seconds later - behind the question
// (a modal panel floats above ordinary windows), larger than it on every side, and dead:
// the window system blocks a window opened under a modal one, so its Close button did
// nothing, and Escape, the natural key to be rid of such a window, goes to the window
// that has the keyboard - the question - and ended it. Now the question is a sheet on the
// main window: part of that window, in front of it, never behind or beside another
// window of ours; and it ends in three ways only - "Go online", "Not now", or the
// application ending. Escape and the window system's "cancel" do not end it. It has no
// time limit. The log says how it ended.
namespace
{
	class CNameDialog : public QDialog
	{
	public:
		using QDialog::QDialog;
		bool strict = true;  // false: as released (tests)
		std::string how;     // how it ended, for the log
		void reject() override
		{
			if(strict && how.empty())
			{
				// not one of the three ways out: Escape, or a cancel sent by the window system
				if(!m_said) Rta::LogLine("online: the name question was asked to go away without an answer (Escape, or a cancel from the window system): it stays - 'Not now' ends it");
				m_said = true;
				return;
			}
			if(how.empty()) how = "it was dismissed (Escape, or its window was closed)";
			QDialog::reject();
		}

	protected:
		void keyPressEvent(QKeyEvent* event) override
		{
			if(event->key() == Qt::Key_Escape && !strict) how = "Escape";
			QDialog::keyPressEvent(event);
		}
		void closeEvent(QCloseEvent* event) override
		{
			if(how.empty()) how = "its window was closed";
			QDialog::closeEvent(event);
		}

	private:
		bool m_said = false;
	};
	QPointer<CNameDialog> g_nameDialog;
	QPointer<QLineEdit> g_nameEdit;
}

void Rta::AskPlayerName(const std::string& why)
{
	if(g_askingName) return;
	g_askingName = true;
	bool released = (Rta::TestDialogs() == 2);
	Rta::LogLine(released ? "online: asking for the player name (dialog, as released 2026-10-13)" : "online: asking for the player name (a sheet on the main window; no time limit)");
	CNameDialog dialog(g_mainWindow);
	dialog.strict = !released;
	auto edit = BuildPlayerName(dialog, why);
	// "Not now" is an answer; Escape is not
	if(auto buttons = dialog.findChild<QDialogButtonBox*>())
	{
		QObject::disconnect(buttons, &QDialogButtonBox::rejected, &dialog, nullptr);
		QObject::connect(buttons, &QDialogButtonBox::rejected, &dialog, [&dialog]() {
			dialog.how = "the Not now button";
			dialog.reject();
		});
	}
	MarkTestWindow(&dialog);
	if(!released && g_mainWindow)
	{
		// a sheet: part of the main window, in front of it, and never behind another window of ours
		dialog.setWindowModality(Qt::WindowModal);
		if(Rta::TestDialogs() == 0)
		{
			if(g_mainWindow->isMinimized()) g_mainWindow->showNormal();
			g_mainWindow->raise();
			g_mainWindow->activateWindow();
			// the application may not be the one in front (a long start, another program
			// used meanwhile): its Dock icon asks for attention
			QApplication::alert(g_mainWindow);
		}
	}
	g_nameDialog = &dialog;
	g_nameEdit = edit;
	bool accepted = dialog.exec() == QDialog::Accepted;
	std::string name = accepted ? edit->text().toStdString() : std::string();
	if(!Rta::OnlineCheckName(name).empty()) name.clear();
	if(!accepted && dialog.how.empty()) dialog.how = g_quitting ? "the application is ending" : "its window went away without an answer";
	Rta::LogLine(name.empty() ? ("online: no player name was given (" + (accepted ? std::string("the name was not usable") : dialog.how) + ")") : "online: a player name was given");
	g_askingName = false;
	Rta::OnlineGiveName(name);
	// the Controls help that was asked for meanwhile
	if(g_controlsWanted && g_mainWindow) QTimer::singleShot(500, g_mainWindow, []() { Rta::ShowControls(g_mainWindow); });
}

// ---- tests: our own windows read and worked without a screen (Rta.h) ------------------------
// The control socket's "ui ..." lands here on the application's own thread, also while a
// question is up (its local event loop runs queued calls).
std::string Rta::UiCommand(const std::string& command)
{
	QStringList words = QString::fromStdString(command).split(' ', Qt::SkipEmptyParts);
	if(words.isEmpty()) return "?";
	auto box = [](QWidget* w) {
		QRect g = w->frameGeometry();
		return QString("%1,%2,%3x%4").arg(g.x()).arg(g.y()).arg(g.width()).arg(g.height());
	};
	if(words[0] == "windows")
	{
		// Qt's top-level windows that are shown, then AppKit's own order, front to back
		QString text;
		for(auto widget : QApplication::topLevelWidgets())
		{
			if(!widget->isVisible()) continue;
			text += QString("[\"%1\" %2 modality=%3 active=%4 box=%5] ").arg(widget->windowTitle(), widget->metaObject()->className()).arg(static_cast<int>(widget->windowModality())).arg(widget->isActiveWindow() ? 1 : 0).arg(box(widget));
		}
		auto modal = QApplication::activeModalWidget();
		text += QString("qt_modal=\"%1\" order: ").arg(modal ? modal->windowTitle() : QString());
		return text.toStdString() + Rta::WindowOrder();
	}
	if(words[0] == "notice") return Rta::Notice();
	if(words[0] == "main" && g_mainWindow)
	{
		if(words.size() >= 2 && words[1] == "raise") g_mainWindow->raise();
		auto label = g_mainWindow->findChild<QLabel*>("rtaNotice");
		auto stacked = g_mainWindow->findChild<QStackedWidget*>("stackedWidget");
		return QString("visible=%1 minimized=%2 box=%3 title=\"%4\" page=%5 notice_shown=%6 notice=\"%7\"")
		    .arg(g_mainWindow->isVisible() ? 1 : 0).arg(g_mainWindow->isMinimized() ? 1 : 0).arg(box(g_mainWindow), g_mainWindow->windowTitle()).arg(stacked ? stacked->currentIndex() : -1)
		    .arg((label && label->isVisible()) ? 1 : 0).arg(label ? label->text() : QString()).toStdString();
	}
	if(words[0] == "name")
	{
		std::string action = (words.size() >= 2) ? words[1].toStdString() : "info";
		if(!g_nameDialog) return "up=0 asking=" + std::string(g_askingName ? "1" : "0");
		auto buttons = g_nameDialog->findChild<QDialogButtonBox*>();
		auto ok = buttons ? buttons->button(QDialogButtonBox::Ok) : nullptr;
		auto notNow = buttons ? buttons->button(QDialogButtonBox::Cancel) : nullptr;
		if(action == "type" && g_nameEdit)
		{
			g_nameEdit->setText(QString::fromStdString(command.substr(command.find("type") + 4)).trimmed());
			action = "info";
		}
		else if(action == "press" && words.size() >= 3)
		{
			if(words[2] == "ok") return (ok && ok->isEnabled()) ? (ok->click(), "pressed: Go online") : "the Go online button is not enabled";
			if(words[2] == "notnow") return notNow ? (notNow->click(), "pressed: Not now") : "no such button";
			if(words[2] == "escape")
			{
				// what the Escape key does to the window that has the keyboard
				QKeyEvent press(QEvent::KeyPress, Qt::Key_Escape, Qt::NoModifier), release(QEvent::KeyRelease, Qt::Key_Escape, Qt::NoModifier);
				QPointer<CNameDialog> dialog = g_nameDialog;
				QApplication::sendEvent(dialog.data(), &press);
				if(dialog) QApplication::sendEvent(dialog.data(), &release);
				return (dialog && dialog->isVisible()) ? "Escape sent: the question is still up" : "Escape sent: the question went away";
			}
			if(words[2] == "close")
			{
				QPointer<CNameDialog> dialog = g_nameDialog;
				dialog->close();
				return (dialog && dialog->isVisible()) ? "close sent: the question is still up" : "close sent: the question went away";
			}
			return "name press ok|notnow|escape|close";
		}
		if(action != "info") return "name info|type TEXT|press ok|notnow|escape|close";
		return QString("up=1 visible=%1 title=\"%2\" modality=%3 sheet=%4 text_length=%5 ok_enabled=%6 box=%7")
		    .arg(g_nameDialog->isVisible() ? 1 : 0).arg(g_nameDialog->windowTitle()).arg(static_cast<int>(g_nameDialog->windowModality())).arg((g_nameDialog->windowModality() == Qt::WindowModal) ? 1 : 0)
		    .arg(g_nameEdit ? g_nameEdit->text().size() : -1).arg((ok && ok->isEnabled()) ? 1 : 0).arg(box(g_nameDialog)).toStdString();
	}
	if(words[0] == "controls")
	{
		std::string action = (words.size() >= 2) ? words[1].toStdString() : "info";
		if(action == "show" && g_mainWindow) Rta::ShowControls(g_mainWindow);
		if(action == "close" && g_controls) g_controls->close();
		if(!g_controls || !g_controls->isVisible()) return std::string("up=0 wanted=") + (g_controlsWanted ? "1" : "0");
		return QString("up=1 title=\"%1\" blocked_now=%2 times_blocked=%3 box=%4").arg(g_controls->windowTitle()).arg(g_controlsBlockedNow ? 1 : 0).arg(g_controlsBlocked).arg(box(g_controls)).toStdString();
	}
	return "ui windows | main info|raise | notice | name info|type TEXT|press ok|notnow|escape|close | controls info|show|close";
}

void Rta::TriggerReset()
{
	if(!g_mainWindow) return;
	// Play!'s own entry: it goes through Rta::BeforeReset like a click in the menu
	if(auto reset = g_mainWindow->findChild<QAction*>("actionReset"))
	{
		if(reset->isEnabled())
			reset->trigger();
		else
			Rta::LogLine("reset: nothing has been started that could be started again");
	}
}

void Rta::SetupWindow(QWidget* window)
{
	auto mainWindow = qobject_cast<QMainWindow*>(window);
	if(!mainWindow) return;
	g_mainWindow = mainWindow;
	// Tests: the control socket is answered by the machine's thread, so a machine that has
	// stopped - or has not been started yet - answers nothing. A file "<control path>.ui"
	// holding "reset", "escape" or "close" is taken up here, on the application's own
	// thread, four times a second; any other line is a "ui" command (Rta::UiCommand)
	// whose answer is written to "<control path>.ui.out".
	if(!Rta::ControlPath().empty())
	{
		auto timer = new QTimer(mainWindow);
		QObject::connect(timer, &QTimer::timeout, mainWindow, [mainWindow]() {
			QFile file(QString::fromStdString(Rta::ControlPath() + ".ui"));
			if(!file.open(QIODevice::ReadOnly)) return;
			QString command = QString::fromUtf8(file.readAll()).trimmed();
			file.close();
			file.remove();
			if(command == "reset" || command == "escape" || command == "close")
			{
				Rta::LogLine("test: '" + command.toStdString() + "' from the .ui file");
				if(command == "reset") Rta::TriggerReset();
				if(command == "escape") Rta::EscapePressed();
				if(command == "close") mainWindow->close();
				return;
			}
			QString answer = QString::fromStdString(Rta::UiCommand(command.toStdString()));
			QFile out(QString::fromStdString(Rta::ControlPath() + ".ui.out.new"));
			if(out.open(QIODevice::WriteOnly | QIODevice::Truncate))
			{
				out.write((command + "\n" + answer + "\n").toUtf8());
				out.close();
				QFile::remove(QString::fromStdString(Rta::ControlPath() + ".ui.out"));
				out.rename(QString::fromStdString(Rta::ControlPath() + ".ui.out"));
			}
		});
		timer->start(250);
	}
	{
		auto onlineMenu = new QMenu("Online", mainWindow);
		auto helpAction = mainWindow->findChild<QMenu*>("menuHelp") ? mainWindow->findChild<QMenu*>("menuHelp")->menuAction() : nullptr;
		mainWindow->menuBar()->insertMenu(helpAction, onlineMenu);
		// the one-step log-in
		auto play = onlineMenu->addAction("Play Online");
		play->setMenuRole(QAction::NoRole);
		play->setToolTip("From the title screen to the lobby's game list by itself.");
		QObject::connect(play, &QAction::triggered, mainWindow, [mainWindow]() { StartOnline(mainWindow, "lobby"); });
		auto host = onlineMenu->addAction("Host a game");
		host->setMenuRole(QAction::NoRole);
		QObject::connect(host, &QAction::triggered, mainWindow, [mainWindow]() { HostGame(mainWindow); });
		auto join = onlineMenu->addAction("Join a game...");
		join->setMenuRole(QAction::NoRole);
		QObject::connect(join, &QAction::triggered, mainWindow, [mainWindow]() { JoinGame(mainWindow); });
		auto stop = onlineMenu->addAction("Stop going online");
		stop->setMenuRole(QAction::NoRole);
		QObject::connect(stop, &QAction::triggered, mainWindow, []() { Rta::OnlineStop(); });
		QAction* atStart = nullptr;
		if(Rta::GetLaunchInfo().packaged)
		{
			atStart = onlineMenu->addAction("Go online at start");
			atStart->setMenuRole(QAction::NoRole);
			atStart->setCheckable(true);
			QObject::connect(atStart, &QAction::triggered, mainWindow, [](bool on) { Rta::SetOnlineAtStart(on); });
		}
		auto forget = onlineMenu->addAction("Forget online login...");
		forget->setMenuRole(QAction::NoRole);
		QObject::connect(forget, &QAction::triggered, mainWindow, [mainWindow]() { ForgetLogin(mainWindow); });
		// what can be chosen follows what is so when the menu opens
		QObject::connect(onlineMenu, &QMenu::aboutToShow, mainWindow, [stop, atStart, forget]() {
			stop->setEnabled(Rta::OnlineActive());
			if(atStart) atStart->setChecked(Rta::OnlineAtStart());
			forget->setEnabled(!Rta::OnlineSavedName().empty());
		});
		onlineMenu->addSeparator();
		auto settings = onlineMenu->addAction("Server, player, patch set...");
		settings->setMenuRole(QAction::NoRole);
		QObject::connect(settings, &QAction::triggered, mainWindow, [mainWindow]() { Rta::ShowOnline(mainWindow); });
		if(Rta::GetLaunchInfo().packaged)
		{
			auto disc = onlineMenu->addAction("Choose the disc image...");
			disc->setMenuRole(QAction::NoRole);
			QObject::connect(disc, &QAction::triggered, mainWindow, [mainWindow]() { Rta::BootDisc(Rta::ChooseDisc(mainWindow, std::string(), true)); });
		}
	}
	auto helpMenu = mainWindow->findChild<QMenu*>("menuHelp");
	if(!helpMenu) helpMenu = mainWindow->menuBar()->addMenu("Help");
	auto controls = new QAction("Controls...", mainWindow);
	controls->setMenuRole(QAction::NoRole);
	QObject::connect(controls, &QAction::triggered, mainWindow, [mainWindow]() { Rta::ShowControls(mainWindow); });
	helpMenu->insertAction(helpMenu->actions().isEmpty() ? nullptr : helpMenu->actions().first(), controls);

	// What the window says in plain words while a folder cannot be read yet (Rta.h,
	// "folders macOS guards"): a line across the top of the window, above the picture or
	// the list of games; it takes room only while there is something to say.
	{
		auto label = new QLabel(mainWindow);
		label->setObjectName("rtaNotice");
		label->setWordWrap(true);
		label->setTextFormat(Qt::PlainText);
		label->setMargin(10);
		label->setStyleSheet("QLabel { background: #fff3c4; color: #1c1c1c; font-size: 14px; font-weight: 600; }");
		label->hide();
		auto central = mainWindow->centralWidget();
		auto grid = central ? qobject_cast<QGridLayout*>(central->layout()) : nullptr;
		auto stacked = mainWindow->findChild<QStackedWidget*>("stackedWidget");
		if(grid && stacked)
		{
			grid->removeWidget(stacked);
			grid->addWidget(label, 0, 0);
			grid->addWidget(stacked, 1, 0);
			grid->setRowStretch(1, 1);
			grid->setVerticalSpacing(0);
		}
		auto timer = new QTimer(mainWindow);
		QObject::connect(timer, &QTimer::timeout, label, [label]() {
			QString text = QString::fromStdString(Rta::Notice());
			if(label->text() != text) label->setText(text);
			if(label->isVisible() != !text.isEmpty()) label->setVisible(!text.isEmpty());
		});
		timer->start(250);
	}

	// Once per data directory: the keys. Not at the start any more, where it came up over
	// the question for the player name (docs/issues/mac-app-start.md): when the game has
	// run for some seconds, nothing of ours is asking anything, and the one-step sign-in
	// is over (it ended at the lobby, or stopped, or was never started). It is also in the
	// Help menu. Not in test runs, unless they test just this.
	auto& config = CAppConfig::GetInstance();
	config.RegisterPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, false);
	if(!config.GetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN) && (!Rta::IsTestRun() || Rta::TestDialogs() != 0))
	{
		auto shown = [mainWindow]() {
			auto& config = CAppConfig::GetInstance();
			config.SetPreferenceBoolean(PREF_RTA_CONTROLS_SHOWN, true);
			// kept even if the application is ended by force later
			config.Save();
			Rta::ShowControls(mainWindow);
		};
		if(Rta::TestDialogs() == 2)
			QTimer::singleShot(2500, mainWindow, shown); // as released
		else
		{
			auto timer = new QTimer(mainWindow);
			auto quiet = std::make_shared<int>(0);
			QObject::connect(timer, &QTimer::timeout, mainWindow, [timer, quiet, shown]() {
				bool free = Rta::FrameCount() > 300 && !g_askingName && !QApplication::activeModalWidget() && !Rta::OnlineActive() && Rta::Notice().empty();
				*quiet = free ? (*quiet + 1) : 0;
				if(*quiet < 3) return;
				timer->stop();
				timer->deleteLater();
				shown();
			});
			timer->start(1000);
		}
	}
}
